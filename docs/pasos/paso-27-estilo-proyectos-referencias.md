# Paso 27 — Estilo común, Proyectos y Referencias

## 1. Objetivo

Segundo paso del [plan de la versión 3.0.0](plan-version-3.md): el estilo común de la interfaz
(pestaña activa, escala de imágenes, letra pequeña, textos de Gradio en español, previsión de
tiempo) y las mejoras de Proyectos y Referencias (B-058 a B-066 y B-079).

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Escala de imágenes (B-079) | Fracción del ancho total: galerías de 2 por fila en una columna del 50 % (Proyectos, Referencias, Bocetos) y de 4 a ancho completo (Composición, Render Final); las pequeñas (tiras de referencias, «Enviado al modelo», miniaturas de partida, imágenes de la auditoría), 6 por fila a ancho completo y 3 en una columna del 50 % |
| Previsión de tiempo (B-064) | Solo cuando Gradio no tiene historial: análisis 45 s, 4 bocetos 35 s, auditoría 30 s, composición o retoque 35 s, render final 30 s, «Otra versión» 25 s |
| «processing» (B-063) | «procesando» |
| Pie en dos líneas (B-065) | Solo en Referencias |

## 3. Implementación

| Entrada | Cambios |
|---------|---------|
| B-058 | CSS de la pestaña seleccionada: blanco, negrita y subrayado (`::after`) blanco |
| B-079 | Rejilla de cada galería por clase (`iai-cols-2/3/4/6`); tiras HTML en rejilla de 6 (3 dentro de `iai-half`); test que comprueba la clase de cada galería |
| B-066 | Letra pequeña común (`SMALL = 0.75rem`) en los elementos de la ficha y en todos los pies de miniatura; los tooltips no cambian |
| B-059 | Proyectos y Referencias en columnas iguales |
| B-060 | Resumen del proyecto sin «Brief», con «Referencias activas» y una línea por etapa |
| B-061 | Vista previa de la referencia con la clase `iai-viewer` (ancho completo y altura según la imagen) |
| B-062 | `Tab.select` de Proyectos recarga galería, portadas y resumen |
| B-065 | `asset_caption` en dos líneas; CSS `white-space: pre` con puntos suspensivos por línea en `#iai-references` |
| B-063 | `launch(i18n=gr.I18n(...))` con los textos de subida en español también para el inglés (`theme.GRADIO_TEXTS`); «processing» es un texto fijo de Gradio sin traducción: el observador de la página lo cambia por «procesando» solo dentro de `.progress-text`. No se traducen los textos del editor de máscara (su CSS y los E2E usan sus etiquetas) |
| B-064 | `ui/forecast.py`: `Forecast` (una `ProcessTime` de Gradio que empieza con la previsión y la descarta en la primera ejecución real) y `seed_forecasts`; las pestañas devuelven sus eventos con coste (y sus «Confirmar») con su previsión. Usa un detalle interno de Gradio, vigilado por un test |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 382 passed |
| `uv run ruff check .` / `ruff format --check` / pre-commit | ✅ |
| Postman en local (mock) | ✅ 53 peticiones, 96 comprobaciones |
| Playwright en local (mock) | ✅ 6/6 (nueva: pestaña activa, recarga de Proyectos y textos de Gradio con el navegador en inglés), en Chromium y en Edge |
| Revisión visual (copia de los datos reales, navegador en inglés) | ✅ «Arrastra el archivo aquí · o · Haz clic para elegirlo» y «procesando \| 0.8/25.1s» desde la primera ejecución |
| Llamadas reales | No hacen falta |
| CI de la PR #39 | ✅ lint y tests, gitleaks, Docker con newman y Playwright |

## 5. Estado final

⏳ En revisión — rama `feat/paso-27`, PR #39.

## 6. Pendiente / futuro

- Paso 28: Bocetos (maquetación a ancho completo y prompts).
