# Paso 13b — Estudio: retoques de zona (inpainting) y render final 16:9

## 1. Objetivo

Retocar una zona de una composición o de un render final sin rehacer la imagen: el usuario
pinta la zona y describe el cambio. Cierra B-009 (recomposición local exacta) y B-018 (render
final con la proporción de la captura).

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| **Render final: opción A** (aprobada): el renderizador regenera la imagen completa con una **guía** (copia reducida con la zona en rojo) y la posición de la zona en el prompt; después se pega en local solo la zona | Misma calidad y resolución que el render; el renderizador no admite máscara | Opción B: `STRUCTURAL_COMPOSER` con máscara sobre el final (zona a 1536 px, más blanda) |
| **Composición: máscara nativa** de `STRUCTURAL_COMPOSER` + recomposición | Su API admite máscara | — |
| Retoque en **composición y render final** (aprobado); bocetos no | Un boceto sale más barato regenerarlo | — |
| Recomposición: zona ampliada y difuminada hacia fuera (12 px; transición de hasta ~24 px), lo pintado se sustituye entero | Sin costuras visibles en la zona | Recorte duro |
| **Se guardan la salida en bruto del modelo, la guía y la máscara** junto al render (petición del usuario) y se ven bajo el visor | Comparar lo que hace el modelo con la recomposición | Guardar solo el resultado |
| **«Usar salida en bruto»**: la imagen completa del modelo como imagen nueva de la etapa, sin coste (petición del usuario) | La regeneración tiene en cuenta toda la escena (sombras, reflejos); el usuario elige en cada caso | — |
| Rechazar un retoque (o su salida en bruto) **repite el retoque** con la misma máscara y los comentarios | Coherente con el rechazo del Paso 10 | Regenerar la etapa entera |
| **16:9 solo en el render final** (aprobado), derivado de la captura original: **1920×1080 exacto** | La composición (GPT-image) solo admite 3 tamaños | — |
| El renderizador trabaja en múltiplos de 16 px: se pide 1920×1088 y se **recorta al centro 4 px arriba y 4 abajo**, sin escalar | Entregar el estándar exacto. La primera versión entregaba 1920×1088 (16:8,8); el usuario lo detectó y se corrigió | Escalar (deforma) o entregar 1088 |
| **Un único render final seleccionado** (petición del usuario): seleccionar uno descarta el anterior | El proyecto tiene un render final; se puede cambiar en cualquier momento | Varios seleccionados |
| Editor: **un `gr.ImageEditor` nuevo por imagen** con `gr.render` | Cambiar por código el valor de un editor montado pierde los trazos una vez sí y otra no (aislado con una app mínima) | Reutilizar el editor |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `shared/src/shared/models.py` | `RenderInpaint` (origen, instrucción, archivos, cobertura, método); `RenderRecord.inpaint` y `raw_of_render_id` |
| `backend/app/pipelines/masks.py` | Máscara del usuario → zona; cobertura (vacía / > 90 %); máscara del modelo; guía; posición en texto; `fit` (recorte al centro); recomposición |
| `backend/app/pipelines/renders.py` | `inpaint_render`, `use_raw_output`, `renderer_size` (proporción exacta), `generation_size` (múltiplo de 16), recorte en `_run_stage`, rechazo de retoques, un único final seleccionado |
| `backend/app/storage/repository.py` | Archivos auxiliares de un render (`sidecars`), a la papelera con él |
| `backend/app/api/v1/renders.py` | `POST /inpaint` (multipart), `GET /inpaint/{mascara\|bruto\|guia}`, `POST /raw` |
| `frontend/ui/` | Cliente (`inpaint_render`, `use_raw_output`), `editor_mask`, «Retocar zona» con `gr.render`, galería del retoque y «Usar salida en bruto» |
| `postman/` | Retoque de la composición, boceto (422), salida en bruto (descarga, uso, 409); fixture `mascara.png` |
| Tests | `test_pipelines_masks.py` (nuevo), retoques en `test_api_renders.py`, `test_ui_studio.py` |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 324 passed |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Postman CLI (mock) | ✅ 44 peticiones, 77 comprobaciones |
| Playwright + Edge en Docker (mock) | ✅ retoque 5/5 (sin pintar → aviso; final 1920×1080 idéntico fuera de la zona; composición con máscara) y Estudio 9/9 (regresión) |
| **Azure, retoque 1** del final `e0f69ed3` («alfombra de yute», zona 11 %) | ✅ 0,0873 € (estimado 0,087 €), 21 s; fuera de la zona idéntico; ⚠️ la alfombra salió **cortada** por el borde |
| **Azure, retoque 2** (prompt con contención y posición) | ✅ 0,0873 €, 19 s. El modelo **ignora** la zona y pone la alfombra bajo el chaise longue; la salida en bruto es natural pero cambia ≈ 17 % de los píxeles de fuera (pana más blanda, geometría desplazada) |
| Decisión del usuario | Salida en bruto del retoque 2 (`d48a5331`) como **render final** del proyecto; el anterior, descartado |

Coste real del paso: **0,175 €**. Proyectos de prueba eliminados (también de la papelera).

Conclusiones: para **añadir objetos**, retocar la composición (máscara nativa) y regenerar el
final a partir de ella; el retoque del final sirve para cambios locales, y la salida en bruto
cuando importa más la coherencia de la escena que conservar cada píxel.

## 5. Estado final

✅ Cerrado — rama `feat/paso-13b`, PR #13 revisada y mergeada por el usuario.

## 6. Pendiente / futuro

- B-020: comprobar si el renderizador acepta 1920×1080 directamente (hoy 1920×1088 + recorte).
- B-009 y B-018 cerrados.
