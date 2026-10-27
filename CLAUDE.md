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
docker compose exec backend python -m app.storage crear "Nombre" --descripcion "Dormitorio principal"
docker compose exec backend python -m app.storage reindexar
# Papelera: vaciar es DEFINITIVO y pide escribir VACIAR (confirmar siempre con el usuario)
docker compose exec backend python -m app.storage papelera listar
docker compose exec backend python -m app.storage papelera restaurar <entrada>
docker compose exec backend python -m app.storage papelera vaciar [--dias N]
```

```bash
# Telemetría: llamadas simuladas (solo mock, sin coste) y resumen de costes
docker compose exec backend python -m app.telemetry simular <id_proyecto> --llamadas 6
curl http://127.0.0.1:8000/api/v1/projects/<id_proyecto>/costs
```

```bash
# Verificación real de Azure (COSTE): solo con AI_PROVIDER_MODE=azure puesto por el usuario
echo s | docker compose exec -T backend python -m app.foundry.smoke --role FAST_DRAFT_MAKER
```

```bash
# API: Swagger en http://127.0.0.1:8000/docs ; pruebas de extremo a extremo con Postman CLI
postman collection run postman/interiorai.postman_collection.json \
  -e postman/local.postman_environment.json --working-dir postman
```

```bash
# Documentación pública (GitHub Pages): https://sergiovelmay.github.io/InteriorAI/
uv run --group docs mkdocs serve           # en local
uv run --group docs mkdocs build --strict  # lo que comprueba la CI
```

```bash
# Interfaz de extremo a extremo (Playwright; app levantada en mock; proyectos «E2E …»)
uv run --group e2e pytest e2e --browser-channel msedge
```
