# Paso 38 — Arreglos de la interfaz

## 1. Objetivo

Séptimo paso del [plan de la versión 4.0.0](plan-version-4.md): los arreglos de la interfaz que
salieron al hacer el manual de usuario (B-104, B-105) y una observación del usuario sobre Costes
IA (B-106). Los precios con la factura real pasan al Paso 39 y la versión, al 40.

## 2. Decisiones tomadas (usuario, 2026-10-27)

| Tema | Decisión |
|------|----------|
| Cuándo | Ahora, sin esperar a los datos de Azure del Paso 39 |
| Detalle de una llamada (B-106) | Se oculta al hacer clic fuera de las celdas del registro y vuelve al estado inicial |

Dentro del propio detalle un clic no lo oculta, para poder seleccionar y copiar sus datos (los
identificadores de la petición). Es la única excepción a «cualquier otro sitio».

## 3. Implementación

| Entrada | Cambios |
|---------|---------|
| B-104 | La estimación junto a cada botón se calculaba una vez al cargar el proyecto con los valores por defecto (4 variantes, calidad media, 4 MP). Ahora `view` guarda en el estado `hint_context` el modo y las imágenes de entrada de bocetos y composición, y `hints` recalcula los textos al cambiar ese estado, las variantes, la calidad de bocetos o de composición o la resolución del render final. Textos con lo elegido: «(8 en calidad alta)», «(1 en calidad baja)», «(a 3.7 MP)» (`draft_hint`, `composition_hint` y `final_hint` en `studio_views.py`) |
| B-105 | El aviso de Costes IA: «Las llamadas con error figuran solo con lo que se conoce (p. ej. las imágenes enviadas al renderizador); el proveedor pudo facturar más (p. ej. un timeout).» |
| B-106 | Botón oculto `#iai-cost-detail-reset` que devuelve el detalle a su texto inicial; `theme.FORCE_DARK_JS` lo pulsa en un clic fuera del registro y del detalle, solo si hay una llamada a la vista |
| Documentación | Manual (Bocetos, Render final y Costes IA), referencia de la interfaz y `docs/agent/gradio_ui.md` |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ Tests nuevos: textos de las estimaciones con distintas opciones y modos, contexto de las estimaciones al cargar el proyecto, y el botón oculto del detalle con su JS |
| Navegador (Playwright, aplicación local en modo simulación con un proxy que anuncia el modo Azure; ningún botón con coste pulsado) | ✅ Bocetos: 4 en calidad media 0,248 € → 8: 0,284 € (lo que calculaba la confirmación) → 8 en calidad alta: 0,492 €. Composición: media 0,071 € → baja 0,065 €, en los dos botones. Render final: 4,0 MP 0,079 € → 16:9 3,7 MP 0,075 € → 1,3 MP 0,045 €. Lo elegido se conserva al cambiar de pestaña. Costes IA: el aviso nuevo; fila → detalle; clic en el detalle → sigue; clic fuera → estado inicial, sin celda resaltada; la misma fila otra vez → detalle; otra pestaña → estado inicial |
| `mkdocs build --strict` | ✅ |
| pre-commit | ✅ |
| CI de la PR #53 | ✅ lint y tests, gitleaks, Docker con newman y Playwright (6 pruebas en 58 s; el trabajo tardó 11 min por la instalación de las dependencias del sistema del navegador, unos 9 min, ajena al cambio), y la construcción de la documentación |

Coste real del paso: 0 €.

## 5. Hallazgo para el Paso 39

En el proyecto del manual hay **5 llamadas reales posteriores a las capturas**, el 27/10 entre
las 15:48 y las 15:55 UTC, hechas por el usuario desde la interfaz: 3 renders finales y 2 prompts, **0,2301 €**.
El proyecto suma 34 llamadas y 1,7959 €. Cuentan en el contraste con la factura del 27/10.

## 6. Estado final

⏳ En revisión — rama `feat/paso-38`.

## 7. Pendiente / futuro

- Paso 39: precios y costes con la factura real (B-098), cuando el usuario aporte los datos.
