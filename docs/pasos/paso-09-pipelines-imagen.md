# Paso 9 — Pipelines de imagen (boceto, composición y render final)

## 1. Objetivo

Generar las imágenes del diseño a partir del **brief aprobado** y de la **captura de SketchUp**
en tres etapas encadenadas, donde cada una exige como entrada un resultado **seleccionado por
el usuario** en la etapa anterior (seleccionar es aprobar).

```
captura SketchUp ──► 1. BOCETO (FAST_DRAFT) ──► el usuario elige
captura + boceto elegido ──► 2. COMPOSICIÓN (STRUCTURAL_COMPOSER) ──► el usuario elige
composición elegida + referencias ──► 3. RENDER FINAL (PHOTOREALISTIC_RENDERER)
```

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| **El boceto edita la captura de SketchUp** (imagen base) (aprobado por el usuario) | Respeta encuadre y distribución desde el principio, como pide el brief. | Texto a imagen. |
| **Render final = composición + imagen de inspiración** como referencias del renderizador (aprobado) | Geometría de la composición y textura real de la pana. | Solo la composición. |
| **Valores por defecto** (aprobados): bocetos 2 × `low`; composición 1 × `medium`; render 1920×1280 | Equilibrio coste/calidad para iterar. | — |
| Entradas a los modelos de imagen hasta **2.048 px** (opción 1 del usuario en la prueba real) | Fidelidad de la captura; el escalado previo más agresivo queda para más adelante si hace falta (B-015). | Reducir a 1.024 px. |
| Tamaños por defecto según la orientación de la captura: GPT-image 1536×1024 / 1024×1536 / 1024×1024; renderizador 1920×1280 / 1280×1920 / 1536×1536 | 3:2 es lo más cercano al 16:9 de SketchUp entre los tamaños de GPT-image. | Tamaño fijo. |
| Validación de tamaños por modelo (GPT-image: 3 tamaños; renderizador: múltiplos de 16 y ≤ 4 MP) | Errores claros (422) antes de llamar y pagar. | Dejar fallar al proveedor. |
| Cada render es un **asset `render`** + `RenderRecord` en `metadatos.json` + **JSON de trazabilidad** junto a la imagen | Descarga con el endpoint de assets; histórico autodescriptivo aunque se pierdan los metadatos. | Solo metadatos. |
| `RenderRecord`: etapa, rol, despliegue, brief y versión, **prompt exacto**, entradas, render padre, lote, tamaño, calidad, semilla, `request_id`, **coste** | Trazabilidad completa de cada imagen. | — |
| Estados del render: `generado → seleccionado | descartado` (y reversibles entre sí), solo por acción del usuario | HITL; el Paso 10 insertará la auditoría antes de la selección. | — |
| Prompt del brief sustituible (`prompt_override`) o ampliable (`extra_instructions`) por ejecución, y se registra lo enviado | Iterar sin crear un brief nuevo. | Editar el brief. |
| Coste por render = coste estimado de la llamada repartido entre sus imágenes | El usuario ve cuánto ha costado cada imagen. | Solo coste por petición. |
| Borrar un render (asset) elimina su registro y mueve su JSON a la papelera | Coherencia del histórico. | — |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `shared/src/shared/models.py` | `RenderStage`, `RenderStatus`, `RenderRecord`, `ProjectMetadata.renders` |
| `backend/app/pipelines/renders.py` | `generate_drafts`, `generate_composition`, `generate_final`, `decide_render`, `approved_brief`, `base_asset`, `selected_render`, `resolve_size`, `build_prompt` |
| `backend/app/api/v1/renders.py` | Endpoints de renders |
| `backend/app/storage/repository.py` | `add_render` (imagen + JSON + asset + registro en una operación); `remove_asset` limpia renders |
| `backend/app/telemetry/metered.py` | `deployment_name()` y `estimate()` públicos |
| `backend/app/api/errors.py` | `RenderNotFoundError` → 404 |
| `postman/interiorai.postman_collection.json` | 8 peticiones de renders en la carpeta protegida «solo mock» |
| `backend/tests/test_api_renders.py` | 18 tests |

## 4. Validación

### Tests, Docker y Postman (mock)

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 235 passed |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Flujo completo en Docker (mock) en un proyecto desechable | ✅ boceto → selección → composición → selección → render final |
| Postman CLI (mock) | ✅ 35 peticiones, 62 asserts, 0 fallos |

Cubierto por tests: bocetos sobre la captura (tamaño, calidad, prompt, lote, coste, archivo +
JSON + descarga), brief no aprobado → 409, prompt sustituido/ampliado, orientación vertical,
tamaños inválidos (422), composición con/sin boceto (no seleccionado → 409), render final
(composición no seleccionada → 409, referencias por defecto y explícitas, referencia inválida
→ 422, tamaños del renderizador), etapa equivocada (422) y render inexistente (404),
transiciones de selección/descarte, historial filtrado, borrado de un render, telemetría.

### Prueba real contra Azure (proyecto real del usuario, brief v1 aprobado)

| # | Llamada | Latencia | Detalle | Coste |
|---|---------|----------|---------|-------|
| 1 | 2 bocetos 1536×1024 `low` (gpt-image-2.5-flare) | 22,0 s | entrada 222 texto / **3.016 imagen**; salida 315 | 0,030525 € |
| 2 | 1 composición 1536×1024 `medium` (gpt-image-2.5-sunburst), captura + boceto A | 21,0 s | entrada 207 texto / **3.044 imagen** (2 imágenes); salida 343 | 0,031396 € |
| 3 | 1 render final 1920×1280 (FLUX.2-pro), composición + inspiración | 15,4 s | 2,46 MP de salida + 3,53 MP de referencias | 0,092274 € |
| | **Total** | | | **0,154195 €** (estimado 0,15–0,18 €) |

Decisiones del usuario (HITL): eligió el **boceto A** («el más exacto con diferencia»),
validó la composición («proporciones y posición perfectas») y seleccionó el render final.
Resultado: tres reposacabezas separados, pana de canalé ancho, chaiselongue en primer plano a
la derecha, península, cocina, terraza y colores de SketchUp conservados; el render final añade
textura realista (pelo de la pana, vivos) y la base de la chaiselongue del producto real. Matiz:
el verde del render salió algo más claro que el «verde-amarillo oscuro» de la inspiración.

Hallazgos de coste:
- En GPT-image **dominan los tokens de imagen de entrada** (≈ 70 % del coste del boceto).
- Con **dos** imágenes de entrada los tokens de imagen fueron prácticamente los mismos que con
  una (3.044 frente a 3.016): la corrección de estimación al alza (0,07–0,09 €) fue errónea;
  la estimación original (0,04–0,06 €) era más cercana al real (0,031 €).
- `medium` a 1536×1024 produjo solo 343 tokens de salida.
- En el renderizador, las **referencias cuestan tanto como la imagen generada** (0,047 € frente a 0,046 €).

## 5. Estado final

✅ Cerrado — rama `feat/paso-09`, PR #8 revisada y mergeada por el usuario.

## 6. Pendiente / futuro

- B-015: escalado automático previo de las imágenes de entrada (sobre todo referencias del
  renderizador) si el coste lo hace necesario.
- Paso 10: auditoría geométrica (GEOMETRIC_AUDITOR) entre `generado` y `seleccionado`.
- Posible nueva iteración del render con el verde más oscuro y apagado (`extra_instructions`).
