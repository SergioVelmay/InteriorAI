# Desarrollo

Cómo preparar el entorno, las convenciones del proyecto y cómo se integran los cambios.

## Entorno

Requisitos: [uv](https://docs.astral.sh/uv/) (instala Python 3.11) y, para las pruebas de la
interfaz, Docker.

```bash
git clone https://github.com/SergioVelmay/InteriorAI.git && cd InteriorAI
uv sync                      # espacio de trabajo: shared, backend y frontend
uvx pre-commit install       # comprobaciones antes de cada commit
uv run pytest                # tests (siempre en modo simulación)
```

El repositorio es un *workspace* de uv con tres paquetes:

| Paquete | Ruta | Contenido |
|---------|------|-----------|
| `interiorai-shared` | `shared/` | Configuración, roles, modelos de dominio y reglas comunes |
| `interiorai-backend` | `backend/` | API FastAPI (`app`) |
| `interiorai-frontend` | `frontend/` | Interfaz Gradio (`ui`) |

Grupos de dependencias aparte: `dev` (tests y ruff, por defecto), `e2e` (Playwright) y `docs`
(esta web).

### Ejecutar sin Docker

```bash
# Backend en simulación (http://127.0.0.1:8000/docs)
cd backend && AI_PROVIDER_MODE=mock DATA_DIR=/tmp/interiorai/data \
  PRICING_FILE=../config/pricing.yaml uv run uvicorn --factory app.main:create_app --port 8000

# Interfaz contra ese backend (http://127.0.0.1:7860)
cd frontend && BACKEND_URL=http://127.0.0.1:8000 DATA_DIR=/tmp/interiorai/data uv run python -m ui
```

Con Docker, `docker compose watch` reconstruye al cambiar `backend/`, `frontend/` o `shared/`.

## Convenciones

| Tema | Convención |
|------|------------|
| Lenguaje | Python 3.11 con anotaciones de tipos obligatorias; Pydantic v2 para modelos y validación |
| Asíncrono | De extremo a extremo en el backend: nada de E/S bloqueante en el bucle de eventos |
| Estilo | `ruff` (lint y formato), líneas de 100 caracteres: `uv run ruff check . --fix` y `uv run ruff format .` |
| Idioma | Identificadores en inglés; textos de la interfaz, documentación y mensajes de commit en español |
| Tests | Junto a cada paquete (`*/tests/`), sin `__init__.py` y con nombres de archivo únicos en todo el repositorio |
| Commits | `tipo: descripción` (`feat`, `fix`, `docs`, `chore`, `test`, `refactor`) |
| Secretos | Solo en `.env` (nunca versionado), leídos con Pydantic Settings y enmascarados |
| IA | Siempre por rol y a través de `FoundryClient`; todo debe funcionar en modo `mock` |
| Datos | Toda escritura en `data/` con el repositorio de proyectos (atómica y con bloqueo) |

Las reglas completas, pensadas también para agentes de IA, están en
[`AGENTS.md`](https://github.com/SergioVelmay/InteriorAI/blob/main/AGENTS.md).

## Flujo de trabajo

1. Cada cambio es un **paso** con su rama `feat/paso-NN` y su documento en la
   [bitácora](https://github.com/SergioVelmay/InteriorAI/tree/main/docs/pasos) (objetivo,
   decisiones, implementación, validación); lo diferido va al
   [backlog](https://github.com/SergioVelmay/InteriorAI/blob/main/docs/pasos/BACKLOG.md).
2. Pull Request a `main`, con la [CI](pruebas.md#integracion-continua) en verde (obligatoria) y
   la rama al día.
3. Revisión y merge. Al publicar una versión: CHANGELOG, versión en los `pyproject.toml`,
   etiqueta y Release.

Si cambias la API, regenera su esquema para esta documentación:

```bash
cd backend && uv run python -m app.openapi   # escribe docs/referencia/openapi.json
```

Un test falla si se te olvida.

## Documentación

Esta web está hecha con [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) a partir
de [`docs/`](https://github.com/SergioVelmay/InteriorAI/tree/main/docs) y `mkdocs.yml`, y se
publica sola en GitHub Pages al integrar en `main`.

```bash
uv run --group docs mkdocs serve             # en local, con recarga
uv run --group docs mkdocs build --strict    # lo que comprueba la CI
```
