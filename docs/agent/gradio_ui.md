# Gradio — interfaz de usuario

> Estado: **esqueleto implementado** (Paso 3). Se completa en los Pasos 11 a 14.

## Estructura y arranque (Gradio 6)

- `frontend/ui/app.py`: `build_app(settings) -> gr.Blocks` (testeable sin lanzar) y
  `launch_kwargs(settings)`; `python -m ui` lanza la app.
- **En Gradio 6 `theme`, `css` y `js` se pasan a `launch()`**, no a `gr.Blocks()`.
- Estado del backend: `fetch_backend_status()` consulta `BACKEND_URL/health` con `httpx`
  async (transporte inyectable para tests) y pinta un badge (`badge()`, HTML escapado).
- Analytics de Gradio desactivados (`GRADIO_ANALYTICS_ENABLED=False`, `analytics_enabled=False`).

## Tema (decisión D5)

`gr.themes.Base(primary_hue="zinc", secondary_hue="slate", neutral_hue="slate")` con
overrides `*_dark` (fondo `#0a0a0a`, superficies `#111113`, bordes `#27272a`, botón primario
claro). Dark mode forzado con `FORCE_DARK_JS` (añade la clase `dark` a `<body>`). Clases CSS
propias con prefijo `iai-`. Todo en `frontend/ui/theme.py`.

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
| Proyectos | Crear / seleccionar / borrar espacios | 11 |
| Assets | Planos, referencias, capturas SketchUp; indexado | 12 |
| Estudio | Notas → prompt → bocetos → composición → auditoría → aprobación → render; `gr.ImageEditor` para máscaras | 13 |
| Costes | KPIs, coste por rol y temporal, tabla detallada | 14 |
