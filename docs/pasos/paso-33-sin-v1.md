# Paso 33 — Retirar la compatibilidad con la v1

## 1. Objetivo

Segundo paso del [plan de la versión 4.0.0](plan-version-4.md): quitar todo lo que solo existía
para la v1 (B-056), con una migración automática que conserva los datos reales.

## 2. Decisiones tomadas (usuario, 2026-10-27)

| Tema | Decisión |
|------|----------|
| Imágenes de la v1 de los datos reales | Se conservan como imágenes sueltas, con su prompt y su coste, sin la cadena de la v1 (brief, rechazos, salidas en bruto ni sus retoques recompuestos) |
| Datos de la 1.0.0 (esquema 1) | Dejan de leerse: quien venga de la 1.0.0 actualiza antes a la 3.0.0 |
| Versión | 4.0.0 (cambio incompatible de la API y del esquema) |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Esquema v3 (`shared/models.py`) | `SCHEMA_VERSION = 3` (el índice `proyectos.json` sigue en el 2, `INDEX_SCHEMA_VERSION`). Fuera `DesignBrief` y su contenido, `BriefStatus`, la ficha de la v1 (`ReferenceAnalysis`, `AssetAnalysis`), `legacy_kind`, los campos de la cadena de la v1 en `RenderRecord` (`brief_id`, `brief_version`, `feedback`, `previous_attempt_id`, `raw_of_render_id`), los de los retoques recompuestos en `RenderInpaint` (`raw_file`, `guide_file`, `feather_px`, `method`) y `RenderAudit.reference_asset_id` |
| Migración v2 → v3 (`app/storage/migrations.py`) | Al arrancar y al restaurar de la papelera, con copia previa en `metadatos.v2.json`; repetible. Las imágenes de la v1 quedan sueltas (los retoques recompuestos, sin su `inpaint`); los archivos no se tocan. Un proyecto en el esquema 1 se registra como error («actualízalo antes con la 3.0.0») y no se lee. Sustituye a la migración v1 → v2 |
| API | Fuera `/briefs` (6 endpoints) y `brief_id` en las peticiones de render. `prompt_override` se mantiene (pruebas sin el PROMPT_ARCHITECT). El coste de la cadena ya no tiene `briefs` |
| Pipelines | Fuera `brief_v1.py`, `hitl/briefs.py`, los prompts `brief_v1.md` y `auditor_captura_v1.md`, las cadenas de la v1 en composición y render final (`approved_brief`, `base_asset`, `_final_v1`, `renderer_size`), el puente `legacy_kind` en `sources.py` y las notas de la v1 del análisis de referencias. La auditoría siempre compara con las referencias del espacio |
| Coste de la cadena (`telemetry/chain.py`) | Sin briefs ni intentos rechazados. **Corrige una discrepancia**: la interfaz decía que incluía las «fichas de referencias», pero en la v2 solo se sumaban las de los briefs. Ahora suma la receta de cada referencia enviada como imagen en la cadena |
| Interfaz | «Ver más» de una imagen de la v1: «Imagen de la v1: anterior al prompt automático»; sin los textos del brief, del rechazo ni de la salida en bruto |
| Postman, E2E y tests | Fuera las 4 peticiones de los briefs; los tests construyen composiciones desde un boceto seleccionado; nuevos tests de la migración v2 → v3 y del coste de la cadena con recetas |
| Documentación | README (actualización desde la 3.x y la 1.0.0), `docs/agent/fast_api_specs.md` y `docs/agent/azure_foundry.md` |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| Migración sobre una copia de los datos reales | ✅ Los tres proyectos pasan al esquema 3 con su `metadatos.v2.json`. «Personalización Cocina Los Molinos» (v2) queda idéntica salvo el número de esquema. Los dos proyectos de prueba conservan sus 19 y 12 imágenes y sus selecciones; en la interfaz se ven con su prompt, sus entradas y su coste, y «Otra versión» desactivada |
| `uv run pytest` | ✅ 361 passed |
| `uv run ruff check .` / `ruff format --check` / pre-commit | ✅ |
| Postman en local (mock, sobre la copia migrada) | ✅ 49 peticiones, 89 comprobaciones |
| Playwright en local (mock), Chromium y Edge | ✅ 6/6 |

Coste real del paso: 0 €.

## 5. Estado final

⏳ En revisión — rama `feat/paso-33`. Al reconstruir Docker tras el merge, los datos reales se
migran al esquema 3 (con su copia `metadatos.v2.json`).

## 6. Pendiente / futuro

- Paso 34: precios y costes con la factura real de Azure (B-098).
