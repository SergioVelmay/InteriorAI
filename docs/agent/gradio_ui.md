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
| Proyectos | Galería con portadas (la imagen más avanzada, B-044), ficha editable (nombre y descripción), crear, activar (por defecto el recordado o el último actualizado, B-025), borrar (papelera); resumen con el coste por rol y desplegable de llamadas (B-027) | 11 · 19 ✅ |
| Referencias | Una sola galería (B-028). Subir de una en una con notas y análisis inmediato (B-029); ficha de casillas de dos niveles por grupo de la receta, con «Marcar todo», «Desmarcar todo» y «Guardar ficha»; «Volver a analizar con estas notas»; sin borrado: descartar = desmarcar todo (B-030) | 12 · 17 · 21 ✅ |
| Estudio | Página única: ① brief (versiones, prompts editables, aprobar/rechazar; se pliega al aprobarlo) → ② bocetos → ③ composición → ④ render final, y un visor común (seleccionar, una imagen por etapa; auditar) | 13a · 17 ✅ |
| Estudio: retoques | «Retocar zona» en el visor (solo composiciones, Paso 17): pincel, instrucción y coste; bajo el visor, la máscara del retoque (y la salida en bruto y la guía de los retoques de la v1) | 13b · 17 ✅ |
| Costes IA | Solo gasto real (B-031). Alcance (proyecto activo / todos), indicadores, gráficos Altair en `gr.Plot` (ancho fijo; series «ROL (despliegue)», leyenda debajo, una por línea; B-032), registro con filtros, detalle de la fila seleccionada y CSV completo (`;`; B-033), precios con tarifas en columnas y unidades (B-034). En el visor del Estudio, coste acumulado de la cadena (con las fichas, Paso 16). Avisos de gasto (Paso 16): distintivo en la cabecera, línea en Costes y `gr.Warning` en el Estudio al lanzar una acción con coste; `BackendClient.cost_alerts()` devuelve `None` si falla (un aviso nunca bloquea) | 14 · 16 ✅ |
