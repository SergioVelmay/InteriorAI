# Gradio — interfaz de usuario

> Estado (2.0.0): **seis pestañas**: Proyectos, Referencias, Bocetos, Composición, Render Final y Costes IA (Pasos 11-14 y 19-24).

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
- Nada que no sea `gr.Tab` como hijo directo de un `gr.Tabs` (ni siquiera `gr.State`): Gradio 6
  duplica en la barra la pestaña seleccionada. Bocetos, Composición y Render Final se crean con
  `build_studio_tabs` dentro del `gr.Tabs` principal; su estado común vive en la primera.
- Estilo común (Paso 27): pestaña activa en blanco y negrita; escala de imágenes por clase de
  galería (`iai-cols-2/3/4/6`: 1/4 del ancho total en galerías, 1/6 en las pequeñas; tiras HTML
  `.iai-thumbs` de 6, o 3 dentro de `iai-half`); letra pequeña `theme.SMALL`; textos de Gradio
  en español con `launch(i18n=...)` (`theme.GRADIO_TEXTS`) y «procesando» por JS en
  `.progress-text`; previsión de tiempo sembrada en la cola de Gradio (`ui/forecast.py`).
- `ImageEditor` del retoque: su valor se envía solo al pulsar (botón puente oculto dentro del
  `gr.render`, accionado por JS en diferido; sincronizarlo en cada trazo bloqueaba la cola) y su
  `preprocess` se sustituye en la instancia por `layers_only` (el fondo y la compuesta podían
  estar a medio escribir en la caché de Gradio). Una subclase del componente generaría un `.pyi`.
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
| Estudio (v1, hasta el Paso 21) | Página única: ① brief (versiones, prompts editables, aprobar/rechazar; se pliega al aprobarlo) → ② bocetos → ③ composición → ④ render final, y un visor común (seleccionar, una imagen por etapa; auditar) | 13a · 17 ✅ |
| Estudio: retoques | «Retocar zona» en el visor (solo composiciones, Paso 17): pincel, instrucción y coste; bajo el visor, la máscara del retoque (y la salida en bruto y la guía de los retoques de la v1) | 13b · 17 ✅ |
| Estudio | Tres pestañas que se desbloquean en orden (B-035, B-043): Bocetos (referencias activas arriba; calidad, formato, variantes 1-8 e indicaciones; miniaturas 2 por fila; prompt automático), Composición y Render Final (provisionales hasta los Pasos 23-24, con retoque y auditoría). En cada una, imagen grande con «Seleccionar» y «Ver más» (interpretación, dudas, prompt, coste de la cadena y lo enviado, B-047); confirmación junto al botón, umbral 0,15 € (B-049). El editor de retoques se vuelve a montar al hacerse visible | 22 ✅ |
| Bocetos · Composición · Render Final | Pestañas de primer nivel (sin «Estudio», Paso 23). Bocetos en 50/50 con tira de lo que se envía (base, apoyos y, con el pie en rojo, los que no caben; `thumbs_html`). Composición: ① auditoría del boceto (miniaturas comparadas, observaciones, «Auditar con IA», informe); ② retoque de la composición seleccionada (editor rojo fijo, sin paleta; instrucción); ③ crear (calidad, formato, «Usar la auditoría», «Usar el retoque», indicaciones, apoyos y dos botones con la miniatura de su imagen de partida); galería e imagen a ancho completo en su proporción, con el texto y lo enviado debajo. Render Final: provisional hasta el Paso 24, sin auditoría. Umbral de confirmación 0,20 €. Referencias: casillas con solo el nombre y el detalle como tooltip (`#iai-sheet-tips` + `MutationObserver` en `theme.FORCE_DARK_JS`) y aviso si hay apoyos que no caben | 23 ✅ |
| Render Final | Proporción (16:9, 3:2 por defecto, 1:1, 2:3, 9:16) y resolución (tres por proporción, la máxima por defecto; `resolution_choices`), indicaciones globales y dos botones con la miniatura de su imagen de partida (composición seleccionada / render final actual). Bajo «Seleccionar», «Otra versión» (solo renders de la v2). Coste por MP (`final_cost`) | 24 ✅ |
| Costes IA | Solo gasto real (B-031). Alcance (proyecto activo / todos), indicadores, leyenda común en HTML (`legend_html`: cada rol con su despliegue actual) junto a «Coste por rol» (50/50), y «Coste por día» y «Coste por proyecto» apilados por rol a ancho completo (Altair en `gr.Plot`, ancho fijo `HALF_WIDTH`/`FULL_WIDTH`; seis colores vivos en `ROLE_COLORS`, una serie por rol actual; B-032, B-080, B-081, Paso 26), registro con filtros, detalle de la fila seleccionada y CSV completo (`;`; B-033), precios con tarifas en columnas y unidades (B-034). En el visor del Estudio, coste acumulado de la cadena (con las fichas, Paso 16). Avisos de gasto (Paso 16): distintivo en la cabecera, línea en Costes y `gr.Warning` en el Estudio al lanzar una acción con coste; `BackendClient.cost_alerts()` devuelve `None` si falla (un aviso nunca bloquea) | 14 · 16 · 26 ✅ |
