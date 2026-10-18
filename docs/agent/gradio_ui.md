# Gradio — interfaz de usuario

> Estado: **shell y pestaña de Proyectos implementados** (Paso 11). Faltan Assets, Estudio y Costes (Pasos 12-14).

## Estructura y arranque (Gradio 6)

- `frontend/ui/app.py`: `build_app(settings, client=None) -> gr.Blocks` (testeable sin lanzar)
  y `launch_kwargs(settings)` (tema, CSS, JS, `allowed_paths=[DATA_DIR]`, `footer_links=[]`);
  `python -m ui` lanza la app.
- `frontend/ui/api_client.py`: `BackendClient` (async, tipado con `shared.models`;
  `X-Request-ID` `ui-…`; errores → `ApiError(status_code, detail)`).
- `frontend/ui/views.py` y `covers.py`: presentación pura (cabecera, resumen, formulario,
  portadas) testeable sin Gradio. `frontend/ui/tabs/<pestaña>.py`: construcción y eventos.
- Manejadores: devuelven `dict` {componente: valor}; errores con `gr.Warning`, éxitos con `gr.Info`.
- Proyecto activo: `gr.BrowserState(storage_key="interiorai.active_project")`.
- `elem_id` estables (`iai-new-name`, `iai-project-name`, `iai-project-description`) para pruebas.
- **En Gradio 6 `theme`, `css` y `js` se pasan a `launch()`**, no a `gr.Blocks()`.
- Analytics de Gradio desactivados (`GRADIO_ANALYTICS_ENABLED=False`, `analytics_enabled=False`).

## Tema (decisión D5)

`gr.themes.Base(primary_hue="zinc", secondary_hue="slate", neutral_hue="slate")` con
overrides `*_dark` (fondo `#0a0a0a`, superficies `#111113`, bordes `#27272a`, botón primario
claro). Dark mode forzado con `FORCE_DARK_JS` (añade la clase `dark` a `<body>`). Clases CSS
propias con prefijo `iai-`. Campos y botones secundarios en zinc (`#18181b`), galería en
tarjetas 3:2 con pie visible. Todo en `frontend/ui/theme.py`.

## Validación visual

Playwright con el Edge instalado (`channel="msedge"`), esperando `wait_until="load"` y un texto
visible («Backend conectado»): Gradio mantiene una conexión abierta (`networkidle` nunca llega) y
`msedge --virtual-time-budget` congela la carga.

## Reglas

- El frontend **no escribe** en `data/`: toda mutación pasa por la API del backend
  (`frontend/ui/api_client.py`, URL en `BACKEND_URL`).
- Puede **leer** imágenes directamente del volumen compartido para previsualizar rápido.
  El volumen se monta **read-only** en el contenedor del frontend (lo garantiza Docker).
- El frontend **no recibe credenciales** de Azure (en compose no usa `env_file`).
- El proyecto activo vive en `gr.State`.
- Ninguna acción de IA avanza de etapa sin un clic explícito de aprobación (HITL).

## Pestañas previstas

| Pestaña | Contenido | Paso |
|---------|-----------|------|
| Proyectos | Galería con portadas, ficha editable, crear, activar, borrar (papelera) | 11 ✅ |
| Assets | Planos, referencias, capturas SketchUp; indexado | 12 |
| Estudio | Notas → prompt → bocetos → composición → auditoría → aprobación → render; `gr.ImageEditor` para máscaras | 13 |
| Costes | KPIs, coste por rol y temporal, tabla detallada | 14 |
