# Paso 51 — La portada del proyecto y las medidas de la geometría

## 1. Objetivo

Dos observaciones del usuario (2026-11-07), las dos de interfaz y **sin coste**:

- **B-118.** En Proyectos, al elegir una tarjeta del final de la galería, la ficha de la derecha
  (nombre, descripción, resumen y llamadas) queda lejos de su miniatura: se pierde de vista qué
  proyecto se está leyendo.
- **B-119.** Las medidas de la superposición del esquema 3D ([Paso 49](paso-49-encuadre.md)) iban
  escritas en rojo, con reborde negro, sobre la propia imagen: tapan la escena y se leen mal.
  Además, las dos comparativas podían verse a la vez, lo que obliga a comparar dos vistas.

## 2. Decisiones (usuario, 2026-11-07)

| Tema | Decisión |
|------|----------|
| Dónde va la portada | Arriba del todo de la columna derecha, antes del resumen |
| Botones sobre la portada | Ninguno: imagen limpia (ni descarga ni pantalla completa) |
| Alcance de la portada | Solo la pestaña Proyectos (Referencias ya tenía su vista previa) |
| Las medidas de la geometría | Fuera de la imagen: debajo del texto de la casilla que elige la comparativa |
| Las dos casillas | **Excluyentes**: al marcar una se desmarca la otra; solo se ve una comparativa a la vez |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| `ui/tabs/projects.py` | `#iai-project-cover` (`gr.Image`, sin botones, `iai-viewer`) sobre el resumen; `detail()` la pone con `cover_image(project, data_dir)` —la misma portada de la tarjeta, B-044— y la oculta sin proyecto; entra en `detail_outputs`, así la actualizan por igual elegir, crear, guardar y la papelera. `ProjectsTab` la expone |
| `ui/geometry.py` | Fuera `_captioned()` y el parámetro `caption` de `overlay()`: la superposición vuelve a ser solo aristas; ya no se importan `ImageDraw` ni `ImageFont` |
| `ui/tabs/studio.py` | Por etapa, `overlay_plain_md` y `overlay_fitted_md` bajo cada casilla, dentro de su columna. `overlay_handler(stage, source)` sabe de qué casilla viene el evento: si esa acaba de marcarse con la otra puesta, la otra sale a `False`; las casillas que no cambian salen con `gr.skip()` para no disparar su propio evento. La medida (`Fidelity.label()` / `Alignment.label()`) va al Markdown y se vacía al desmarcar |
| `ui/theme.py` | `.iai-geometry`: la medida pegada a su casilla, en letra pequeña, con alto mínimo para que la fila no salte al aparecer |
| Documentación | Manual (Proyectos y Bocetos), referencia de la interfaz y `docs/agent/gradio_ui.md` |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 387 passed. Tests nuevos: la portada se ve con el proyecto activo y se oculta sin ninguno (`test_ui_app.py`); las casillas excluyentes, la medida bajo cada una y la vuelta a la imagen al desmarcar (`test_ui_studio.py`); la superposición ajustada ya no escribe el rótulo (`test_ui_geometry.py`) |
| `uv run ruff check .` / `ruff format` | ✅ |
| `mkdocs build --strict` | ✅ |
| pre-commit | ✅ |
| Playwright de extremo a extremo | ⚠️ 5 de 8; los 3 fallos son `page.goto: net::ERR_ABORTED` con el frontend respondiendo 200. **Pasan exactamente igual con el código de `main`** (se reconstruyó la imagen sin estos cambios para comprobarlo) y sueltas pasan: intermitencia del entorno local, anotada como B-120 |
| Comprobación en el navegador (Playwright, modo simulación) | ✅ Proyectos: la portada se ve sobre la ficha a todo el ancho de la columna y cambia al elegir otro proyecto. Bocetos: «tal cual» da «35 % a ±3 px · 53 % a ±8 px» bajo su casilla; al marcar la ajustada, la otra se desmarca sola, su medida desaparece y su vista se oculta; al desmarcar, vuelve la imagen sin medidas |
| CI de la PR #73 | ✅ lint y tests, gitleaks, Docker con newman y Playwright (las 8 pruebas de extremo a extremo, en Chromium) y la construcción de la documentación. Que ahí pasen las tres que fallaban en local confirma B-120 |

Coste del paso: 0 € (todo en modo simulación).

## 5. Estado final

✅ Cerrado — rama `feat/paso-51`, PR #73 mergeada en `main` (2026-11-07), commit `936f377`.

## 6. Pendiente / futuro

- B-117 (el zum del encuadre) sigue abierto: esto no lo toca.
- B-116 sigue a la espera de la prueba real en `azure`.
