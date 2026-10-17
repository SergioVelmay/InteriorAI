# Paso 3 — Esqueleto Docker

## 1. Objetivo

Levantar backend (FastAPI) y frontend (Gradio) en contenedores aislados con docker-compose,
comunicados por red interna y compartiendo el volumen `studio_shared_data` → `./data`, con
la funcionalidad mínima para verificar la infraestructura.

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| Backend y frontend como miembros del workspace `uv` (`interiorai-backend` → paquete `app`, `interiorai-frontend` → paquete `ui`) | Un único `uv.lock`; `uv sync` en la raíz instala todo para tests locales. | Entornos separados. |
| Dockerfile multi-stage: builder con `uv sync --frozen --no-dev --package <svc> --no-editable`; runtime solo con `/opt/venv` | Imágenes reproducibles desde el lock, sin código fuente ni `uv.lock` en runtime. | `pip install` en una sola etapa. |
| Contexto de build = raíz del repo | Ambos servicios necesitan `uv.lock` y `shared/`. | Contexto por servicio. |
| Usuario sin privilegios uid 1000 en ambas imágenes | Mínimo privilegio. | Ejecutar como root. |
| Servicio de un solo uso **`data-init`** (imagen del backend, root, `chown 1000:1000 /app/data`), con `pull_policy: never`; el backend depende de él (`service_completed_successfully`) | En Docker Desktop (Windows) el bind mount aparece como `root:root 755` y el uid 1000 no puede escribir (verificado). El `chown` hecho desde el contenedor persiste. `pull_policy: never` evita un intento de descarga de una imagen local en un clon nuevo (verificado). | Backend como root; entrypoint con `gosu`; permisos 777. |
| Volumen con nombre `studio_shared_data` (driver `local`, `o: bind`, `device: ./data`) | Requisito del proyecto. Compose resuelve la ruta relativa a absoluta y Docker Desktop crea `./data` si no existe (verificado). | Bind mount directo `./data:/app/data`. |
| Frontend monta el volumen **read-only** | Docker garantiza la regla "solo el backend escribe en `data/`". | Confiar solo en la convención. |
| Frontend **sin `env_file`**: solo recibe `APP_ENV`, `LOG_LEVEL`, `DATA_DIR`, `BACKEND_URL`, `FRONTEND_PORT` | El frontend nunca necesita credenciales de Azure (verificado: 0 variables `AZURE_*`/`DEPLOYMENT_ROLE_*`). | `env_file: .env` en ambos. |
| Puertos publicados solo en `127.0.0.1` | La app no queda expuesta a la red local. | `8000:8000`. |
| App factory `create_app(settings)` + `uvicorn --factory`, sin instancia global | Los tests inyectan `Settings`; importar el módulo no lee `.env`. | `app = FastAPI()` a nivel de módulo. |
| `/health` devuelve `503 degraded` si `DATA_DIR` no es escribible | El `HEALTHCHECK` de Docker detecta un volumen inutilizable (así se detectó el problema de permisos). | Healthcheck que solo comprueba que el proceso responde. |
| `HEALTHCHECK` con `python -c urllib` | `python:3.11-slim` no incluye `curl`. | Instalar `curl`. |
| `docker compose watch` con `action: rebuild` | La instalación no editable obliga a reconstruir; la caché de capas lo hace rápido. | Montar el código fuente como volumen. |
| Gradio 6.30: `theme`/`css`/`js` en `launch()` (`launch_kwargs()`), dark mode forzado por JS | Cambio de API en Gradio 6. | API de Gradio 4/5. |
| `pytest-asyncio` (`asyncio_mode = "auto"`) | Tests async del frontend (y del backend en pasos futuros). | Plugin de anyio con marcadores. |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `backend/pyproject.toml` | `interiorai-backend`: fastapi, uvicorn[standard], shared |
| `backend/app/__init__.py` | `__version__` desde metadatos del paquete |
| `backend/app/main.py` | `create_app()`, lifespan, `SettingsDep`, `GET /health` |
| `backend/Dockerfile` | Multi-stage, uid 1000, healthcheck |
| `backend/tests/test_api_health.py` | 4 tests |
| `frontend/pyproject.toml` | `interiorai-frontend`: gradio, httpx, shared |
| `frontend/ui/theme.py` | Tema D5, CSS `iai-*`, `FORCE_DARK_JS` |
| `frontend/ui/app.py` | `build_app()`, `fetch_backend_status()`, `badge()`, `launch_kwargs()`, `main()` |
| `frontend/ui/__main__.py` | `python -m ui` |
| `frontend/Dockerfile` | Multi-stage, uid 1000, analytics desactivados, healthcheck |
| `frontend/tests/test_ui_app.py` | 6 tests |
| `docker-compose.yml` | `data-init`, `backend`, `frontend`, volumen `studio_shared_data` |
| `pyproject.toml`, `uv.lock` | Nuevos miembros, `httpx` + `pytest-asyncio` en dev, testpaths |
| `ruff.toml` | `known-first-party` += `app`, `ui` |
| `AGENTS.md` (regla 8), `CLAUDE.md`, `README.md`, `docs/agent/{fast_api_specs,gradio_ui}.md` | Documentación |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 39 passed (29 shared + 4 backend + 6 frontend) |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| `docker compose ps` | ✅ `data-init` Exited (0); `backend` y `frontend` healthy |
| `curl 127.0.0.1:8000/health` | ✅ `{"status":"ok","version":"0.1.0","mode":"mock","data_dir_writable":true}` |
| `curl 127.0.0.1:7860/` | ✅ 200 |
| Frontend → backend por red interna | ✅ "Backend conectado · modo mock" |
| Backend escribe en `/app/data` → aparece en `./data` del host | ✅ |
| Frontend intenta escribir en `/app/data` | ✅ `Read-only file system` |
| Usuario de los contenedores | ✅ `uid=1000(app)` en ambos |
| Variables Azure en el frontend | ✅ 0 |
| `.env`, `uv.lock`, `/src` dentro de las imágenes | ✅ No existen |
| Puertos | ✅ Solo `127.0.0.1:8000` y `127.0.0.1:7860` |
| Clon nuevo (sin imágenes, sin volumen, sin `./data`) | ✅ Arranca sin errores; `./data` se crea |

Problemas encontrados y resueltos durante el paso:
1. Backend `unhealthy` (503) en el primer arranque → permisos del bind mount en Docker Desktop → servicio `data-init`.
2. En un clon nuevo, compose intentaba descargar `interiorai-backend:dev` de Docker Hub → `pull_policy: never`.

## 5. Estado final

🧪 En validación — rama `feat/paso-03`, Pull Request en GitHub.

## 6. Pendiente / futuro

- B-005: UID/GID configurable para hosts Linux cuyo usuario no sea 1000 (Paso 15).
