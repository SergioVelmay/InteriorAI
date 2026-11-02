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
| CI de la PR #63 | ✅ lint y tests, gitleaks, Docker con newman y Playwright, y la construcción de la documentación |

Coste real del paso: 0 €.

## 5. Antes de publicar: CI de `main` en rojo (B-114)

Tras el merge, la CI de `main` falló en Playwright (también la del merge del Paso 44), aunque
las de las dos PRs habían pasado: pruebas intermitentes. Reproducido en local (1 fallo de 7 en
tres de cuatro pasadas) y con dos causas:

| Causa | Arreglo |
|-------|---------|
| La aplicación: el botón «Confirmar: mover a la papelera» tenía el id `iai-confirm-delete` (B-111) y el bloqueo detectaba las confirmaciones de coste por el prefijo `iai-confirm-`: con la papelera por confirmar, bloqueaba lo demás, también su «Cancelar» | Id `iai-delete-confirm`; las confirmaciones de coste se reconocen por su clase `.iai-cost-confirm`, no por el nombre |
| Las pruebas: esperaban a que el botón estuviera libre, pero algunas cargas empiezan una fracción de segundo después (p. ej. al recargar la página) y el clic caía ya bloqueado; y el texto de una opción («16:9») no está marcado, lo está su etiqueta | Cada acción espera a que no haya nada en marcha en dos lecturas seguidas y a que ni el elemento ni lo que lo contiene estén bloqueados (`e2e/conftest.py`) |

Validación: con la papelera por confirmar, «Cancelar» y «Confirmar» libres (navegador); E2E en
local 4 de 4 pasadas sin fallos; `uv run pytest` ✅; CI de la PR #64 ✅ dos veces (la segunda,
relanzando el trabajo de Docker y extremo a extremo). La etiqueta `v4.1.0` irá sobre el merge de
este arreglo.

## 6. Estado final

⏳ En revisión — rama `feat/paso-45`. Tras el merge y con la CI de `main` en verde: etiqueta
`v4.1.0` y Release de GitHub con el OK del usuario.
