# InteriorAI

[![CI](https://github.com/SergioVelmay/InteriorAI/actions/workflows/ci.yml/badge.svg)](https://github.com/SergioVelmay/InteriorAI/actions/workflows/ci.yml)

Estudio de interiorismo asistido por IA con supervisión humana (Human-in-the-Loop),
construido con FastAPI, Gradio y Azure AI Foundry.

> 🚧 En desarrollo. Estado de los pasos: [docs/pasos/README.md](docs/pasos/README.md).

## Puesta en marcha

Requisitos: [uv](https://docs.astral.sh/uv/) (instala Python 3.11 automáticamente).

```bash
cp .env.example .env        # rellena tus valores; .env nunca se sube a git
uvx pre-commit install      # activa los hooks de seguridad (gitleaks, bloqueo de .env)
uv sync                     # crea el entorno
uv run python -m shared     # comprueba tu configuración (la clave se muestra enmascarada)
uv run pytest               # tests
```

Sin credenciales de Azure, la aplicación funciona en modo `AI_PROVIDER_MODE=mock`.
### Docker

Requisitos: Docker Desktop (o Docker Engine + Compose v2).

```bash
docker compose up --build -d
```

| Servicio | URL |
|----------|-----|
| Interfaz (Gradio) | http://127.0.0.1:7860 |
| API (FastAPI) | http://127.0.0.1:8000/docs |

Prueba de extremo a extremo de la API con [Postman CLI](https://learning.postman.com/docs/postman-cli/postman-cli-overview/):

```bash
postman collection run postman/interiorai.postman_collection.json \
  -e postman/local.postman_environment.json --working-dir postman
```

Pruebas de la interfaz con [Playwright](https://playwright.dev/python/) (con la app levantada
en modo mock; crean proyectos «E2E …» y los mueven a la papelera al terminar):

```bash
uv run --group e2e playwright install chromium   # una vez
uv run --group e2e pytest e2e                    # o --browser-channel msedge con el Edge instalado
```

La CI (GitHub Actions) ejecuta en cada Pull Request lint, tests, gitleaks sobre todo el
historial, la construcción de las imágenes, la colección de Postman (con newman) y las pruebas
de Playwright, siempre en modo mock y sin secretos. Seguridad: [SECURITY.md](SECURITY.md).

Los proyectos y renders se guardan en `./data` (volumen `studio_shared_data`), que nunca
se sube a git. En Linux, crea antes la carpeta con `mkdir -p data`.
