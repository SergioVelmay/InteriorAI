# Gradio — interfaz de usuario

> Estado: **diseño** (Paso 1). Se completa en los Pasos 11–14.

## Tema (decisión D5)

`gr.themes.Base(primary_hue="zinc", neutral_hue="slate")` + dark mode forzado +
CSS custom (fondo `#0a0a0a`). Centralizado en `frontend/ui/theme.py`.

## Reglas

- El frontend **no escribe** en `data/`: toda mutación pasa por la API del backend
  (`frontend/ui/api_client.py`, URL en `BACKEND_URL`).
- Puede **leer** imágenes directamente del volumen compartido para previsualizar rápido.
- El proyecto activo vive en `gr.State`.
- Ninguna acción de IA avanza de etapa sin un clic explícito de aprobación (HITL).

## Pestañas previstas

| Pestaña | Contenido | Paso |
|---------|-----------|------|
| Proyectos | Crear / seleccionar / borrar espacios | 11 |
| Assets | Planos, referencias, capturas SketchUp; indexado | 12 |
| Estudio | Notas → prompt → bocetos → composición → auditoría → aprobación → render; `gr.ImageEditor` para máscaras | 13 |
| Costes | KPIs, coste por rol y temporal, tabla detallada | 14 |
