# Paso 56 — Versión 4.2.0

## 1. Objetivo

Publicar la 4.2.0 con lo hecho en los Pasos 46 a 55 (B-115 a B-126). La línea principal es
**B-116**: que bocetos, composiciones y renders respeten los volúmenes del esquema 3D de
SketchUp, poder superponerlo y medir cuánto se parecen.

Antes de publicar, rehacer las tres capturas del manual que quedaron desfasadas con el
[Paso 55](paso-55-superposicion.md) (**B-126**).

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Versión | **4.2.0** (2026-11-08): funciones nuevas sin cambios incompatibles |
| Capturas | Rehacer las tres de la superposición **antes** de publicar, para que la web no salga con una interfaz que ya no existe |
| Publicación | Etiqueta y Release solo con el OK del usuario, tras el merge y con la CI de `main` en verde |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Versión | `4.2.0` en los cuatro `pyproject.toml` (y en `/health`), `uv.lock` y `docs/referencia/openapi.json` |
| CHANGELOG | «Sin publicar» pasa a `[4.2.0] — 2026-11-08`. Las entradas describen el **estado final** de cada función, no el camino: la superposición se cuenta una vez, tal como queda tras el Paso 55, en lugar de encadenar lo que cambió en los Pasos 47, 49, 51 y 55 |
| README y web | Versión 4.2.0; página Versiones con la fila nueva y la nota «Desde la 4.1.0 a la 4.2.0» (sin cambios en el `.env` ni migración; `indications` es un campo nuevo que la 4.1.0 ignora) |
| Capturas (B-126) | `bocetos-superposicion.jpg`, `composicion-superposicion.jpg` y `render-superposicion.jpg`, rehechas |
| Bitácora | Cierre del Paso 55 con su merge; B-123 a B-126 resueltas; B-116 pasa a «publicado en la 4.2.0» y conserva lo único que le falta, la prueba real en `azure` |

### Las capturas (B-126)

Tomadas con Playwright sobre la aplicación levantada en `AI_PROVIDER_MODE=mock`, con el proyecto
real **«Diverso Getafe 3 5B Cocina y Desayunero»**, que tiene esquema 3D en las tres etapas. El
guion solo navega, marca una casilla y fotografía: **no genera ni modifica nada** y no hubo
ninguna llamada a IA.

Cada captura recoge el visor, el título, el apartado «Fidelidad al esquema 3D», las dos casillas y
la opacidad. La de Composición usa la casilla **corregida** a propósito, porque esa imagen tiene un
desplazamiento real del encuadre (6 px a la izquierda · 32 px arriba) y así se ve para qué sirve.

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run ruff check .` y `uv run ruff format --check .` | ✅ |
| `uv run pytest` | ✅ 388 passed (incluye el esquema OpenAPI con la versión nueva) |
| `uvx pre-commit run --all-files` | ✅ |
| `uv run --group docs mkdocs build --strict` | ✅ |
| `/health` tras reconstruir Docker | ✅ `version` 4.2.0, `mode` `mock` |
| CI de la PR [#80](https://github.com/SergioVelmay/InteriorAI/pull/80) | ✅ Lint y tests (1m 5s), gitleaks de todo el historial (10 s), Docker y extremo a extremo (5m 12s), documentación (12 s). Publicar en GitHub Pages se omitió, como corresponde en una PR |

Coste real del paso: **0 €**. Ninguna llamada a IA.

## 5. Estado final

Pendiente de completar tras el merge.

## 6. Pendiente / futuro

- **B-116**: queda la prueba real en `azure` (una composición con boceto + esquema y otra solo con
  el esquema, sobre la misma partida, midiendo las dos con la superposición). Unos 0,24 €,
  anunciando antes cada llamada.
- **B-024** (Gradio sigue exigiendo `pillow<13`), **B-103** (Material for MkDocs llega al fin de
  vida el 5 de mayo de 2027) y **B-120** (E2E intermitentes en local con Edge) siguen abiertas.
