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

<!-- Se ampliará con docker compose (Paso 3) y Postman CLI (Paso 5). -->
