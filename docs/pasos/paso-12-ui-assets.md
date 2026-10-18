# Paso 12 — Interfaz: pestaña Assets

## 1. Objetivo

Gestionar desde la interfaz el material de entrada del proyecto activo: subir capturas de
SketchUp, planos y referencias, verlos, anotarlos y borrarlos, e **indexar y validar las fichas**
de las referencias (la puerta HITL de la entrada), hasta ahora solo accesible por API o scripts.

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| **Subpestañas por tipo** (Capturas · Planos · Referencias) (aprobado por el usuario) | Cada tipo tiene su papel en el flujo. | Una galería con filtro. |
| **Indexación manual** con el botón «Indexar referencias pendientes» (aprobado) | El usuario decide cuándo se llama a la IA; junto al botón se indica el coste (≈ 0,0004 €/referencia en Azure) y al terminar se muestra el real. | Indexar al subir. |
| **Planos solo como imagen** (PNG, JPEG, WebP), petición del usuario | Un PDF nunca llegaba a los modelos (se omitía con aviso); el plano en imagen sirve de contexto del brief, de imagen base alternativa a la captura y de referencia de auditoría. Cierra B-013 («no aplica»). | Mantener PDF. |
| El frontend lee los archivos subidos (temporal de Gradio) y los envía a la API; nunca escribe en `data/` | Regla de mínimo privilegio (volumen en solo lectura). | — |
| Subida múltiple con nota común; errores por archivo (duplicado 409, formato 415, tamaño 413) como avisos | Flujo rápido sin perder el detalle de cada fallo. | — |
| Ficha editable con listas separadas por comas, medidas vacías permitidas y «origen» obligatorio si hay medidas | Coherente con «nunca inventar medidas». | — |
| `gr.skip()` en lugar de `{}` cuando un manejador no cambia nada (**bug latente** también en Proyectos) + test de regresión | Gradio interpreta `{}` como un único valor y el evento falla. | — |
| Lectura no bloqueante de los archivos subidos (`anyio.Path`) | Detectado por el lint (`ASYNC240`). | `Path.read_bytes()` en una corrutina. |
| Pulido pedido por el usuario: **barras de desplazamiento oscuras** (zinc) en toda la app y **sin hueco bajo las galerías** (`min-height` de 450 px de Gradio anulado) | Coherencia visual. | Dejarlo para el final. |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `backend/app/api/uploads.py`, `backend/app/api/v1/assets.py`, `backend/app/pipelines/{images,prompt_engineer}.py` | Planos solo imagen; mensajes genéricos |
| `frontend/ui/api_client.py` | `list_assets`, `upload_asset`, `update_asset_note`, `delete_asset`, `index_references` (timeout de IA), `validate_analysis` |
| `frontend/ui/views.py` | `asset_caption`, `asset_info_md`, `analysis_status`, `analysis_form_values`, `parse_analysis_form`, catálogos de la ficha |
| `frontend/ui/tabs/assets.py` | `build_assets_tab`: subpestañas, galerías, subida, detalle, nota, papelera, indexación y ficha |
| `frontend/ui/tabs/projects.py` | `gr.skip()` en los manejadores |
| `frontend/ui/app.py` | Pestaña Assets; se recarga al entrar (`Tab.select`) con el proyecto activo |
| `frontend/ui/theme.py` | Barras de desplazamiento y altura de galerías |
| Tests | `test_ui_assets.py` (10), regresión `return {}` en `test_ui_app.py`; backend: PDF rechazado en todos los tipos, catálogo, brief con captura + plano |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 274 passed (28 del frontend) |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| `/asset-kinds` en Docker | ✅ planos: `image/jpeg`, `image/png`, `image/webp` |
| Prueba funcional con Playwright + Edge (proyecto de prueba) | ✅ 7/7: pestaña con el proyecto activo · captura subida · PDF en Planos rechazado · 2 referencias con nota común · indexación (mock) · nota guardada + ficha corregida y validada · referencia a la papelera |
| Capturas en Docker | ✅ Proyectos sin hueco bajo la galería; Assets con el proyecto real (fichas validadas 285 × 160 × 87 cm, notas) |

Problemas encontrados y resueltos: devolución de `{}` en manejadores (bug latente), lectura
bloqueante de archivos, hueco de galería (`min-height` de Gradio), botón de indexación partido en
tres líneas. Sin llamadas reales a la IA: coste 0 €. Proyectos de prueba eliminados.

Nota: los textos internos de Gradio («Drop File Here») siguen el idioma del navegador; en el
navegador de pruebas (inglés) aparecen en inglés.

## 5. Estado final

🧪 En validación — rama `feat/paso-12`, Pull Request en GitHub.

## 6. Pendiente / futuro

- Nada nuevo para el backlog. B-013 queda cerrado («no aplica»: los planos son imágenes).
