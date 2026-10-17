@AGENTS.md

## Comandos

```bash
# Entorno (uv workspace, Python 3.11)
uv sync
uv run pytest
uv run python -m shared           # comprueba el .env (clave enmascarada)

# Hooks de seguridad y estilo
uvx pre-commit install
uvx pre-commit run --all-files

# Lint / format
uv run ruff check . --fix
uv run ruff format .
```

```bash
# Docker (backend :8000, frontend :7860, solo en 127.0.0.1)
docker compose up --build -d
docker compose ps                 # data-init Exited (0), backend/frontend healthy
docker compose logs -f backend
docker compose watch              # desarrollo: reconstruye al cambiar backend/, frontend/, shared/
docker compose down
```

```bash
# Almacenamiento (dentro del contenedor)
docker compose exec backend python -m app.storage listar
docker compose exec backend python -m app.storage crear "Nombre" --tipo dormitorio
docker compose exec backend python -m app.storage reindexar
```

<!-- Se ampliará con Postman CLI (Paso 5). -->
