## Resumen

<!-- Qué cambia y por qué. Enlaza la issue si la hay (p. ej. «Cierra #12»). -->

## Cómo se ha probado

<!-- Tests nuevos o actualizados, pruebas manuales en modo simulación, capturas si cambia la interfaz. -->

## Comprobaciones

- [ ] `uv run pytest` y `uv run ruff check . && uv run ruff format --check .` pasan
- [ ] pre-commit pasa (`uvx pre-commit run --all-files`)
- [ ] Sin secretos, `.env` ni `data/`, y sin nombres comerciales de modelo en el código (solo roles)
- [ ] Funciona en modo simulación (`AI_PROVIDER_MODE=mock`)
- [ ] Documentación al día (`docs/`, `mkdocs build --strict`) si cambia el comportamiento; esquema de la API regenerado si cambia la API
- [ ] Commits en español con el formato `tipo: descripción`
