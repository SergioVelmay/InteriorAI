# AGENTS.md — InteriorAI

## Brief

InteriorAI es un estudio de interiorismo asistido por IA con supervisión humana
(**Human-in-the-Loop**): a partir de planos, capturas de SketchUp y referencias
(Ikea/Pinterest) genera bocetos, composiciones y renders fotorrealistas por
habitación. **Ninguna etapa del pipeline avanza sin aprobación explícita del usuario.**

- **Backend**: Python 3.11 + FastAPI (async). Única fuente de escritura sobre `data/`.
- **Frontend**: Gradio, tema oscuro zinc/slate. Lee imágenes del volumen; escribe vía API.
- **IA**: Azure AI Foundry, accedido **solo por rol funcional**, nunca por nombre de modelo.
- **Entorno**: docker-compose, volumen compartido `studio_shared_data` → `./data`.
- **Repositorio público**: la seguridad de secretos es crítica.

## Reglas críticas (no negociables)

1. **Cero secretos en el código.** Credenciales, API keys y endpoints se leen de `.env`
   mediante Pydantic Settings (`shared.settings.get_settings()`). Nunca se hardcodean ni se loguean
   (usar `SecretStr`). `.env` jamás se versiona; las variables nuevas se añaden a `.env.example`.
2. **Cero nombres comerciales de modelo en el código.** Se usa el enum de roles
   (`PROMPT_ENGINEER`, `GEOMETRIC_AUDITOR`, `REFERENCE_ANALYST`, `FAST_DRAFT`,
   `STRUCTURAL_COMPOSER`, `PHOTOREALISTIC_RENDERER`). Los nombres solo aparecen en
   `.env.example` y `config/pricing.yaml`. Despliegue de un rol: `settings.deployment_for(role)`.
3. **Escritura atómica** de todo JSON en `data/` (temp + `os.replace`) bajo lock por proyecto:
   usar siempre `ProjectRepository` (`backend/app/storage/`), nunca escribir a mano. Única
   excepción: la telemetría (`costes_telemetria.jsonl`) solo añade líneas; una línea cortada al
   final se ignora al leer (`app/storage/telemetry_log.py`).
4. **Toda llamada a IA pasa por `FoundryClient`** (`backend/app/foundry/`, dependencia `FoundryDep`)
   para que la telemetría de costes la registre. Nunca llamar a Azure por otra vía. Las llamadas
   hechas por un proyecto van dentro de `with telemetry_scope(project_id):`. **Nunca reintentar
   un timeout** (pudo facturarse); solo 429/503.
5. **Todo debe funcionar en `AI_PROVIDER_MODE=mock`** sin credenciales; los tests usan mock.
   Las llamadas reales (script `python -m app.foundry.smoke` o la API en modo `azure`) solo
   cuando el usuario active el modo `azure`, anunciando antes cada llamada y su coste estimado.
6. **Human-in-the-Loop**: las transiciones de estado (briefs, iteraciones) solo ocurren por
   acción del usuario, a través de `app/hitl/` (`ensure_transition`). Nunca se inventan medidas:
   lo que no conste va a `null` y, si hay dudas, a `open_questions`.
7. `data/` contiene datos del usuario: nunca se versiona ni se borra sin confirmación
   (el borrado de la app es suave: mueve a `data/.papelera/`).
8. **Mínimo privilegio en contenedores**: usuario sin privilegios (uid 1000), puertos publicados
   solo en `127.0.0.1`, el frontend sin credenciales y con `data/` en solo lectura.

## Estilo de código

- Python 3.11, type hints obligatorios, Pydantic v2 para modelos y validación.
- Async de extremo a extremo en el backend (sin I/O bloqueante en el event loop).
- `ruff` (lint + format, config en `ruff.toml`), línea máx. 100.
- Identificadores en inglés; textos de UI, docs y mensajes de commit en español.
- Tests con `pytest` junto a cada paquete (`*/tests/`), **sin `__init__.py`** y con nombres de
  archivo únicos en todo el repo (p. ej. `test_settings.py`, `test_api_health.py`).
- Commits: `tipo: descripción` (`feat`, `fix`, `docs`, `chore`, `test`, `refactor`).

## Flujo de trabajo

- Desarrollo incremental por pasos: rama `feat/paso-NN` → Pull Request en GitHub → validación
  del usuario en el PR → merge a `main`.
- Cada paso se documenta en `docs/pasos/paso-NN-*.md`; lo diferido va a `docs/pasos/BACKLOG.md`.
- Índice y estado de pasos: [docs/pasos/README.md](docs/pasos/README.md).

## Mapa de rutas

| Ruta | Contenido |
|------|-----------|
| `shared/src/shared/` | `settings.py` (configuración), `roles.py` (roles y tipo de API), `models.py` (dominio) |
| `backend/app/` | FastAPI: `api/`, `core/`, `storage/`, `foundry/`, `telemetry/`, `pipelines/`, `hitl/` |
| `frontend/ui/` | Gradio: `app.py`, `theme.py`, `api_client.py`, `tabs/` |
| `config/pricing.yaml` | Precios por despliegue en EUR (sin secretos; montado en solo lectura) |
| `postman/` | Colección (flujo completo de la API v1), entorno local y `fixtures/` |
| `data/` | Volumen de proyectos (gitignored): `proyectos.json`, `{id}/...` |
| `docs/agent/` | Contexto técnico por materia (leer solo cuando aplique) |
| `docs/pasos/` | Bitácora de pasos y backlog |

## Documentación por materia (leer bajo demanda)

- Integración con Azure AI Foundry, roles y costes → [docs/agent/azure_foundry.md](docs/agent/azure_foundry.md)
- API FastAPI, almacenamiento y convenciones → [docs/agent/fast_api_specs.md](docs/agent/fast_api_specs.md)
- Interfaz Gradio, tema y pestañas → [docs/agent/gradio_ui.md](docs/agent/gradio_ui.md)
