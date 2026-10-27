# Paso 31 — Capturas y versión 3.0.0

## 1. Objetivo

Último paso del [plan de la versión 3.0.0](plan-version-3.md): las capturas del README con el
caso de demostración del usuario (B-023), los detalles que vio mientras lo completaba (B-090 a
B-093) y la publicación de la 3.0.0.

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Dónde capturar | En la aplicación del usuario tal cual (modo `azure`, con todos sus proyectos), solo navegando: sin copias, mock ni proyectos de prueba, y sin ninguna acción con coste |
| Datos visibles | Tal cual: el proyecto es público y sin ánimo de lucro; no importa que se vean marcas, nombres comerciales o imágenes de referencia |
| Capturas | Seis, una por pestaña y a página completa, con las selecciones del usuario y todos los desplegables abiertos (sin captura propia del retoque: sale en Composición). En Referencias, la primera referencia |
| Proyecto | «Personalización Cocina Los Molinos» |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| «Procesando» (B-090) | Junto a los botones con coste ocupa la línea del coste (o de la confirmación), sin el icono que Gradio recortaba (`.iai-action-note`). Al pulsar «Confirmar (con coste)», el cuadro se oculta al instante (`.click(...).then(...)`, sin cola): el «procesando» queda junto al botón y no se puede confirmar dos veces |
| Correcciones de la auditoría (B-091) | Con ajuste de línea, como el prompt enviado |
| Tooltip de Costes IA (B-092) | Gradio pone 6 px de relleno al lienzo de Altair y Vega calcula el ratón desde el borde exterior: la zona del tooltip quedaba desplazada respecto a la barra. Sin ese relleno (`.altair canvas`) |
| Orden de los roles (B-093) | Primero los de texto (REFERENCE_ANALYST verde, PROMPT_ARCHITECT morado, GEOMETRY_AUDITOR azul) y después los de imagen (FAST_DRAFT_MAKER amarillo, COMPOSITION_BUILDER naranja, REALISTIC_RENDERER rojo), en la leyenda, en «Coste por rol» y en el apilado |
| Capturas (B-023) | Playwright sobre `http://127.0.0.1:7860` a 1920 px (contenedor de 1440 px), solo mirando: elige el proyecto y la primera referencia para verlos, despliega secciones y espera a que no quede nada cargando. JPEG en `docs/img/` (3,3 MB en total). Composición, la más larga, en dos (petición del usuario): `04-A` con la auditoría y el retoque y `04-B` desde «Crear composición», cada una por debajo del límite de 1 MB del pre-commit sin comprimirla más que las demás |
| README | Sección «Recorrido» con las seis capturas, cada una en un desplegable; versión 3.0.0; costes orientativos con lo medido en la 3.0.0 |
| Versión | `3.0.0` en los cuatro `pyproject.toml` (y en `/health`), `uv.lock` actualizado |
| CHANGELOG | «Sin publicar» pasa a `[3.0.0] — 2026-10-27`, con un resumen, la nota de actualización y lo corregido en este paso |
| Dependencias (B-024) | Gradio 6.30.0, la última publicada, sigue exigiendo `pillow<13`: se mantiene el `override-dependencies` de Pillow 13 y B-024 sigue abierto. Sin alertas de Dependabot ni PRs abiertas |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| «Procesando» y confirmación | ✅ En mock: el texto en la línea del coste; con un proxy que hacía pasar el backend mock por `azure` (sin coste), 8 bocetos con confirmación: el cuadro se oculta al confirmar y el botón vuelve al terminar |
| Tooltip | ✅ Centro y 2 px dentro de cada borde de cada barra, a 1500 y 1920 px: el tooltip correcto, también en una barra de 12 px |
| `uv run pytest` | ✅ 383 passed |
| `uv run ruff check .` / `ruff format --check` / pre-commit | ✅ |
| Postman en local (mock) | ✅ 53 peticiones, 96 comprobaciones; `/health` con la versión 3.0.0 |
| Playwright en local (mock), Chromium y Edge | ✅ 6/6 |
| Capturas | ✅ Seis pestañas (Composición en dos), completas y sin nada cargando, revisadas una a una |
| CI de la PR #43 | ✅ lint y tests, gitleaks, Docker con newman y Playwright |

Coste real del paso: 0 €.

## 5. Estado final

✅ Cerrado — rama `feat/paso-31`, PR #43 revisada y mergeada por el usuario (2026-10-27). Con su
OK, etiqueta `v3.0.0` sobre `a41e396` y [GitHub Release «InteriorAI 3.0.0»](https://github.com/SergioVelmay/InteriorAI/releases/tag/v3.0.0)
(2026-10-27), con las notas del CHANGELOG. Docker reconstruido: `/health` devuelve la versión 3.0.0.

## 6. Pendiente / futuro

- B-024: quitar el `override-dependencies` de Pillow cuando Gradio admita Pillow 13.
