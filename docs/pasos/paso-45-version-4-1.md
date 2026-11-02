# Paso 45 — Versión 4.1.0

## 1. Objetivo

Último paso del [plan de la versión 4.1.0](plan-version-4-1.md): publicar la 4.1.0 con lo hecho
en los Pasos 41 a 44 (B-107 a B-113).

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Versión | 4.1.0 al terminar (2026-11-02): funciones nuevas sin cambios incompatibles |
| Publicación | Etiqueta y Release solo con el OK del usuario, tras el merge y la CI de `main` en verde |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Versión | `4.1.0` en los cuatro `pyproject.toml` (y en `/health`), `uv.lock` y `docs/referencia/openapi.json` |
| CHANGELOG | «Sin publicar» pasa a `[4.1.0] — 2026-11-02`, con un resumen y la nota de actualización; enlace a la Release |
| README y web | Versión 4.1.0; nota «Desde la 4.0.0» (sin cambios en el `.env` ni migración; el estado `descartado` no lo lee la 4.0.0); página Versiones con la 4.1.0 |
| Dependencias (B-024) | Gradio 6.31.0, la última publicada, sigue exigiendo `pillow<13`: B-024 sigue abierto. Sin alertas de Dependabot ni PRs abiertas |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ (incluye el esquema OpenAPI con la versión nueva) |
| `mkdocs build --strict` | ✅ |
| pre-commit | ✅ |

Coste real del paso: 0 €.

## 5. Estado final

⏳ En revisión — rama `feat/paso-45`. Tras el merge y con la CI de `main` en verde: etiqueta
`v4.1.0` y Release de GitHub con el OK del usuario.
