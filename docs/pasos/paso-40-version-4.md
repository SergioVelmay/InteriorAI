# Paso 40 — Versión 4.0.0

## 1. Objetivo

Último paso del [plan de la versión 4.0.0](plan-version-4.md): publicar la 4.0.0 con todo lo
hecho en los Pasos 32 a 39.

## 2. Decisiones tomadas (usuario, 2026-10-29)

| Tema | Decisión |
|------|----------|
| Alcance | Versión, CHANGELOG, README y web; etiqueta y Release solo con el OK del usuario tras el merge y la CI de `main` en verde |
| B-024 (Pillow 13) | Solo si Gradio ya lo admite; si no, fuera de la 4.0.0 |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Versión | `4.0.0` en los cuatro `pyproject.toml` (y en `/health`), `uv.lock` actualizado y `docs/referencia/openapi.json` regenerado |
| CHANGELOG | «Sin publicar» pasa a `[4.0.0] — 2026-10-29`, con un resumen y la nota de actualización; enlace a la Release |
| README | Versión 4.0.0; nota «Desde la 3.x» con la variable nueva y opcional `PROMPT_ARCHITECT_TIMEOUT_S` |
| Web | Versiones: la 4.0.0 con su fecha y su Release; la variable nueva en «Desde la 3.x a la 4.0.0» |
| Dependencias (B-024) | Gradio 6.31.0, la última publicada, sigue exigiendo `pillow<13`: se mantiene el `override-dependencies` de Pillow 13 y B-024 sigue abierto. Sin alertas de Dependabot ni PRs abiertas |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ (incluye el test del esquema OpenAPI con la versión nueva) |
| `mkdocs build --strict` | ✅ |
| pre-commit | ✅ |
| CI de la PR #55 | ✅ lint y tests, gitleaks, Docker con newman y Playwright, y la construcción de la documentación |

Coste real del paso: 0 €.

## 5. Estado final

✅ Cerrado — rama `feat/paso-40`, PR #55 revisada y mergeada por el usuario (2026-10-29). Con la
CI de `main` en verde y el OK del usuario: etiqueta anotada `v4.0.0` sobre `ebe4630` y
[Release «InteriorAI 4.0.0»](https://github.com/SergioVelmay/InteriorAI/releases/tag/v4.0.0),
la última, con las notas del CHANGELOG (enlaces relativos a `blob/v4.0.0/`). Docker reconstruido:
`/health` responde la versión 4.0.0. El enlace de la página Versiones de la web funciona.

En las notas se quitó una frase desfasada de la entrada de la documentación pública («el manual
de usuario y la referencia técnica, en preparación»); el CHANGELOG se corrige en este cierre.
