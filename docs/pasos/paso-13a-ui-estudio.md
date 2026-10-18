# Paso 13a — Interfaz: pestaña Estudio (ciclo HITL)

## 1. Objetivo

Recorrer desde la interfaz el ciclo completo con supervisión humana del proyecto activo, hasta
ahora solo accesible por API: **brief → bocetos → composición → render final**, con selección,
descarte, rechazo con comentarios (y regeneración) y auditoría geométrica a demanda. El Paso 13
se divide en dos (aprobado por el usuario); el editor de máscaras e inpainting va al **13b**.

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| **Dividir el Paso 13** en 13a (ciclo HITL) y 13b (máscaras, endpoint de inpainting, B-009 y B-018) (aprobado) | PR revisables; el 13b añade backend nuevo. | Un único paso. |
| **Página única vertical** con 4 secciones (① Brief · ② Bocetos · ③ Composición · ④ Render final) y un **visor común** (aprobado) | Se ve el recorrido completo; las acciones sobre una imagen están en un solo sitio. | Subpestañas por etapa. |
| **Confirmación con segundo clic solo en modo Azure y por encima de 0,05 €** (aprobado) | Brief, composición, render final y auditoría cuestan; un boceto suelto no. En simulación no molesta. | Confirmar siempre / nunca. |
| Coste estimado junto a cada botón (límite alto de lo observado en las pruebas reales) y coste real al terminar | Transparencia antes y después de gastar. | — |
| Progreso con avisos al empezar y terminar + temporizador de Gradio (cierra **B-014**) | Las llamadas duran de segundos a minutos (auditoría) y Gradio ya muestra el tiempo transcurrido. | Tareas en segundo plano. |
| Prompts de imagen **editables** solo con el brief propuesto; se guardan antes de aprobar | El usuario revisa lo que se enviará a los modelos (HITL). | Editar tras aprobar. |
| La sección del brief **se pliega sola** cuando el brief mostrado está aprobado | El trabajo continúa en las imágenes; se puede desplegar. | — |
| Valores por defecto: boceto y composición **seleccionados más recientes**; referencias del brief aprobado | Menos clics en el flujo habitual; todo es modificable. | — |
| Visor: abre el render final seleccionado más reciente; descarga y pantalla completa nativas | — | — |
| Rechazar con comentarios **y regenerar** o **sin regenerar**; casilla para aplicar las correcciones de la última auditoría | Mismas opciones que la API (Paso 10). | — |
| Timeouts del cliente: 600 s para IA y 1000 s para la auditoría (por encima del timeout del backend, 900 s) | El backend corta antes; nunca se reintenta un timeout. | — |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `frontend/ui/api_client.py` | Briefs (`list/create/update/approve/reject_brief`) y renders (`list_renders`, `generate_renders`, `decide_render`, `reject_render`, `audit_render`) con timeouts de IA |
| `frontend/ui/studio_views.py` | Presentación pura: costes y umbral de confirmación, brief en Markdown (medidas desconocidas como `?`), pies y detalle de renders, informe de auditoría |
| `frontend/ui/tabs/studio.py` | `build_studio_tab`: secciones, visor, confirmación, acciones y vista única `view()` |
| `frontend/ui/app.py` | Pestaña Estudio, recargada al entrar con el proyecto activo |
| `frontend/tests/test_ui_studio.py` | 14 tests: presentación, estimaciones, peticiones del cliente (rutas, cuerpos y timeouts) y vista de la pestaña (brief plegado, botones, galerías, visor) |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 288 passed (42 del frontend) |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Prueba funcional con Playwright + Edge (proyecto de prueba, modo simulación) | ✅ 9/9: Estudio con el proyecto activo · brief generado · prompt editado (comprobado en la API, también en el prompt de los bocetos) y brief aprobado · 2 bocetos y uno seleccionado · composición · render final · auditoría · rechazo con comentarios, regeneración y nueva selección · sin confirmaciones en simulación |
| Capturas en Docker con el proyecto real | ✅ brief aprobado plegado, bocetos, composiciones y renders con su estado y coste, visor con el render final definitivo |

Problema encontrado y resuelto: la prueba funcional editaba el prompt antes de que la interfaz
mostrara el brief nuevo (el aviso aparece antes de actualizar la vista) y la edición se
sobrescribía. Se espera a la vista actualizada y se comprueba el resultado en la API.

Sin llamadas reales a la IA: coste 0 €. Proyectos de prueba eliminados (también de la papelera).

## 5. Estado final

🧪 En validación — rama `feat/paso-13a`, Pull Request en GitHub.

## 6. Pendiente / futuro

- Paso 13b: editor de máscaras (`gr.ImageEditor`), endpoint de inpainting, recomposición local
  exacta (B-009) y render final con la proporción de la captura (B-018).
- B-014 cerrado (progreso con avisos y temporizador).
