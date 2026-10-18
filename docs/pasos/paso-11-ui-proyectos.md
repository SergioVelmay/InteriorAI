# Paso 11 — Interfaz: shell, tema y pestaña de Proyectos

## 1. Objetivo

Estructura definitiva de la aplicación Gradio (cabecera, pestañas, tema) y primera pestaña
funcional, **Proyectos**: crear, ver, editar, activar y borrar espacios. El frontend **lee**
imágenes del volumen (solo lectura) y **escribe** solo a través de la API.

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| **Galería visual con portadas** (aprobado por el usuario) | Identificación inmediata de cada espacio. | Tabla compacta. |
| **Proyecto activo recordado en el navegador** (`gr.BrowserState`) (aprobado) | Al recargar se sigue en el mismo proyecto. | Solo durante la sesión. |
| Portada automática: render final seleccionado → último render no rechazado ni descartado → captura → plano → imagen de relleno con la inicial | Siempre hay una imagen representativa, sin intervención. | Portada manual. |
| Indicador del **modo de IA** en la cabecera («Simulación · sin coste» / ámbar «Azure · con coste») | El usuario siempre sabe si una acción tiene coste. | — |
| `BackendClient` tipado con los modelos de `shared`; errores → `gr.Warning` con el mensaje en español del backend | Frontend y backend no pueden desincronizarse en los campos. | Diccionarios sin tipar. |
| `X-Request-ID` con prefijo `ui-` | Distinguir en la telemetría las acciones de la interfaz. | — |
| Funciones de presentación puras (`views.py`, `covers.py`) separadas de Gradio | Testeables sin navegador. | Lógica dentro de los manejadores. |
| Borrado con doble confirmación y mensaje de papelera recuperable | Regla 7: no perder datos del usuario. | Borrado directo. |
| Tema: campos y botones secundarios en zinc casi negro (`#18181b`), sin el pie de Gradio (`footer_links=[]`), galería sin botones (`buttons=[]`), tarjetas 3:2 con pie siempre visible | Aspecto oscuro premium coherente; el `slate` por defecto azuleaba los campos. | Valores por defecto de Gradio. |
| Pie de tarjeta sin repetir el tipo cuando coincide con el nombre | «Estudio · Estudio» era redundante. | — |
| `elem_id` estables en los campos clave | Pruebas de interfaz que no dependen del orden de los campos. | Selectores por posición. |
| `allowed_paths=[DATA_DIR]` en `launch()` | Gradio solo sirve las portadas desde el volumen si se autoriza. | — |
| Validación visual con **Playwright + Edge instalado** (`channel="msedge"`, sin descargar navegadores) | Capturas y prueba funcional reales; `msedge --virtual-time-budget` congela la carga de Gradio. | Captura con Edge sin ventana a secas. |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `frontend/ui/api_client.py` | `BackendClient`, `ApiError`, `Health` |
| `frontend/ui/covers.py` | `cover_asset`, `cover_image`, `placeholder`, `asset_path` |
| `frontend/ui/views.py` | `badge`, `header_html`, `gallery_caption`, `project_summary_md`, `form_values`, `parse_form` |
| `frontend/ui/tabs/projects.py` | `build_projects_tab` (galería, ficha, creación, guardado, borrado) → `ProjectsTab` |
| `frontend/ui/app.py` | Cabecera, pestañas (Assets, Estudio y Costes como «próximamente»), `BrowserState`, `launch_kwargs` |
| `frontend/ui/theme.py` | Colores de campos y botones, CSS de cabecera, indicadores y galería |
| Tests | `test_ui_api_client.py` (7), `test_ui_views.py` (7), `test_ui_app.py` (4) |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 262 passed (18 del frontend) |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Carga de la pestaña dentro del contenedor contra el backend real | ✅ 0,21 s; portada = render final v2 (PNG) |
| Capturas con Playwright (local y Docker) | ✅ cabecera con estado, modo y proyecto activo; galería 3:2 con pies; ficha con resumen y formulario |
| Prueba funcional con Playwright | ✅ crear → activo; editar y guardar; recargar → proyecto recordado; borrar con doble confirmación → papelera |

Resumen del proyecto real en la ficha: 1 captura, 2 referencias, brief v1 aprobado, 2 bocetos,
2 composiciones, 2 renders finales, render final elegido y **0,45 € en 10 llamadas** (coincide con
la suma de las pruebas reales de los Pasos 8 a 10).

Problemas encontrados y resueltos durante el paso:
1. Galería con una sola imagen a todo el ancho y pie oculto → CSS de cuadrícula 3:2.
2. Campos con fondo azulado (`slate`) → colores zinc en el tema.
3. Captura con `msedge --virtual-time-budget`: la carga de Gradio no termina → Playwright.
4. Pruebas de interfaz frágiles (`nth(1)`, campos que desaparecen al cerrar el desplegable) →
   `elem_id` estables. Los proyectos de prueba se eliminaron (también de la papelera).

Sin llamadas a la IA en todo el paso: coste 0 €.

## 5. Estado final

✅ Cerrado — rama `feat/paso-11`, PR #10 revisada y mergeada por el usuario. Pulido pedido por el
usuario (barra de desplazamiento oscura y hueco bajo la galería) resuelto en el Paso 12.

## 6. Pendiente / futuro

- B-019: incorporar las pruebas de interfaz con Playwright al repositorio y a la CI (Paso 15).
- ~~Pulido: hueco vacío bajo la galería~~ → resuelto en el Paso 12.
