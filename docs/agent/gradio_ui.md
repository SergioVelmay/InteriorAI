# Gradio — interfaz de usuario

> Estado: **las cuatro pestañas implementadas** (Pasos 11-14).

## Estructura y arranque (Gradio 6)

- `frontend/ui/app.py`: `build_app(settings, client=None) -> gr.Blocks` (testeable sin lanzar)
  y `launch_kwargs(settings)` (tema, CSS, JS, `allowed_paths=[DATA_DIR]`, `footer_links=[]`);
  `python -m ui` lanza la app.
- `frontend/ui/api_client.py`: `BackendClient` (async, tipado con `shared.models`;
  `X-Request-ID` `ui-…`; errores → `ApiError(status_code, detail)`).
- `frontend/ui/views.py`, `studio_views.py` y `covers.py`: presentación pura (cabecera, resumen, formulario,
  portadas) testeable sin Gradio. `frontend/ui/tabs/<pestaña>.py`: construcción y eventos.
- Manejadores: devuelven `dict` {componente: valor}; errores con `gr.Warning`, éxitos con `gr.Info`.
  **Nunca devolver `{}`** (Gradio lo toma como un único valor y el evento falla): usar
  `{componente: gr.skip()}` (`unchanged()` en cada pestaña; hay un test que lo vigila).
- Pestañas que dependen del proyecto activo se recargan al entrar (`Tab.select`).
- Lectura de archivos en manejadores asíncronos con `anyio.Path` (no bloquear el bucle).
- Proyecto activo: `gr.BrowserState(storage_key="interiorai.active_project")`.
- `elem_id` estables con prefijo `iai-` (`iai-new-name`, `iai-gen-brief`, `iai-drafts`,
  `iai-select`…) para las pruebas: no renombrarlos sin actualizar las pruebas de Playwright.
- **En Gradio 6 `theme`, `css` y `js` se pasan a `launch()`**, no a `gr.Blocks()`.
- **`gr.ImageEditor`: no cambiar su valor por código** con el editor ya montado (una vez sí y
  otra no llega sin la capa de trazos). Se crea uno nuevo por imagen con `gr.render`
  (`triggers=[shown_render.change]`, `concurrency_limit=1` para no duplicar la `key`).
- Pruebas de Playwright con el editor: desplazar el lienzo a la vista antes de pintar (los
  eventos de ratón fuera de la ventana se pierden). En Windows sin Docker, la caché de subidas de
  Gradio puede leer a medias un fondo idéntico subido varias veces: probar el editor en Docker.
- Analytics de Gradio desactivados (`GRADIO_ANALYTICS_ENABLED=False`, `analytics_enabled=False`).

## Tema (decisión D5)

`gr.themes.Base(primary_hue="zinc", secondary_hue="slate", neutral_hue="slate")` con
overrides `*_dark` (fondo `#0a0a0a`, superficies `#111113`, bordes `#27272a`, botón primario
claro). Dark mode forzado con `FORCE_DARK_JS` (añade la clase `dark` a `<body>`). Clases CSS
propias con prefijo `iai-`. Campos y botones secundarios en zinc (`#18181b`), galería en
tarjetas 3:2 con pie visible. Todo en `frontend/ui/theme.py`.

## Validación visual y pruebas de extremo a extremo

Pruebas en `e2e/` (pytest-playwright, grupo `e2e`; fuera de `uv run pytest`): Proyectos, Assets,
Estudio, retoques y Costes, con proyectos propios «E2E …» que se mueven a la papelera al terminar.
Se niegan a ejecutarse si el backend no está en mock. En local, `--browser-channel msedge`; en la
CI, Chromium. Claves:

- Esperar `wait_until="load"` y un texto visible («Backend conectado»): Gradio mantiene una
  conexión abierta (`networkidle` nunca llega).
- `UI.activate` recarga la página: el proyecto pudo crearse por API después de abrirla.
- Los avisos (`gr.Info`) aparecen **antes** de que la vista se actualice: esperar al estado nuevo
  (p. ej. el valor de un desplegable) antes de interactuar.
- `expect` con 30 s (Gradio tarda en actualizar tras cada evento).

## Reglas

- El frontend **no escribe** en `data/`: toda mutación pasa por la API del backend
  (`frontend/ui/api_client.py`, URL en `BACKEND_URL`).
- Puede **leer** imágenes directamente del volumen compartido para previsualizar rápido.
  El volumen se monta **read-only** en el contenedor del frontend (lo garantiza Docker).
- El frontend **no recibe credenciales** de Azure (en compose no usa `env_file`).
- El proyecto activo vive en `gr.BrowserState` (sobrevive a recargas).
- Ninguna acción de IA avanza de etapa sin un clic explícito de aprobación (HITL).
- Cada acción de IA muestra su coste estimado (`studio_views.COST_*`, límite alto de lo
  observado); en modo `azure` las de más de 0,05 € piden un **segundo clic** de confirmación.
- Progreso de las llamadas largas: `gr.Info` al empezar y al terminar (con el coste real) y el
  temporizador propio de Gradio en los componentes afectados.

## Pestañas previstas

| Pestaña | Contenido | Paso |
|---------|-----------|------|
| Proyectos | Galería con portadas, ficha editable, crear, activar, borrar (papelera) | 11 ✅ |
| Assets | Subpestañas Capturas · Planos · Referencias: subir (solo imágenes), ver, nota, papelera; indexar (manual) y validar fichas | 12 ✅ |
| Estudio | Página única: ① brief (versiones, prompts editables, aprobar/rechazar; se pliega al aprobarlo) → ② bocetos → ③ composición → ④ render final, y un visor común (seleccionar, descartar, rechazar con comentarios, auditar) | 13a ✅ |
| Estudio: retoques | «Retocar zona» en el visor (composición y final): pincel, instrucción y coste; bajo el visor, salida en bruto, guía y máscara del retoque, y «Usar salida en bruto» | 13b ✅ |
| Costes | Alcance (proyecto activo / todos), «Incluir simulación» (desmarcada), indicadores, coste por rol, por día (apilado por rol) y por proyecto (`gr.BarPlot`, colores por rol, eje Y desde 0), registro de llamadas con filtros y CSV (`;`), precios vigentes. En el visor del Estudio, coste acumulado de la cadena (con las fichas, Paso 16). Avisos de gasto (Paso 16): distintivo en la cabecera, línea en Costes y `gr.Warning` en el Estudio al lanzar una acción con coste; `BackendClient.cost_alerts()` devuelve `None` si falla (un aviso nunca bloquea) | 14 · 16 ✅ |
