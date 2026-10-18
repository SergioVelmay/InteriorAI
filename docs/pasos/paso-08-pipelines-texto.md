# Paso 8 — Pipelines de texto (CONTEXT_MANAGER y PROMPT_ENGINEER)

## 1. Objetivo

Primeras etapas inteligentes del flujo: el **CONTEXT_MANAGER** convierte cada referencia
(Ikea, Pinterest...) en una ficha estructurada y el **PROMPT_ENGINEER** combina notas, planos,
capturas de SketchUp y fichas en un **brief técnico de diseño** con los prompts para los modelos
de imagen. Primera puerta Human-in-the-Loop: ninguna imagen se generará (Paso 9) a partir de un
brief no aprobado por el usuario.

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| **Prompts de imagen en inglés**; resto del brief y UI en español (aprobado por el usuario) | Los modelos de imagen (FLUX especialmente) siguen mejor el inglés. | Todo en español. |
| **Ciclo de aprobación del brief ya en este paso** (aprobado) | El Paso 9 necesita un brief aprobado como entrada. | Posponerlo al Paso 10. |
| **Material real del usuario** para la prueba (aprobado): captura de SketchUp, planificador de IKEA e inspiración | Resultados representativos. | Material sintético. |
| Ficha `ReferenceAnalysis`: medidas solo de la nota del usuario o legibles en la imagen; si no, `null` + `dimensions_source: desconocido` | Regla de oro: nunca inventar cotas. | Estimaciones del modelo. |
| Fichas `proposed` → `validated` cuando el usuario las revisa (`PUT .../analysis`) | HITL también en el conocimiento de entrada; el brief distingue la autoridad de cada ficha. | Fichas sin revisión. |
| Nota del usuario por asset (`description`, al subir o con `PATCH`) | El usuario aporta medidas y contexto que la imagen no muestra. | — |
| Brief con jerarquía de fuentes: SketchUp/planos > fichas validadas y notas > fichas propuestas > inspiración | Las capturas son la verdad geométrica; la inspiración solo aporta textura y color. | — |
| Al brief, **las referencias van como texto** (fichas), no como imágenes; solo capturas y planos como imagen (máx. 4) | Ya analizadas por luna: no pagar dos veces tokens de imagen en un modelo ~20 veces más caro. | Reenviar todas las imágenes. |
| Imágenes reducidas a 1.024 px de lado largo, JPEG (transparencias sobre blanco), nunca ampliadas | Control de tokens de imagen. | Imagen original. |
| Planos en PDF no se envían (aviso en el brief) | La Responses API admite `input_file`, pero hay que verificarlo en Azure (B-013). | — |
| **Esquemas estrictos generados desde Pydantic** (`strict_schema`) | Una sola definición; sin `$ref`, todas las propiedades obligatorias, sin palabras clave no admitidas. | Esquemas JSON escritos a mano. |
| Prompts de sistema en `backend/app/pipelines/prompts/*.md` con versión = hash del contenido | Ajustables sin tocar código; cada salida guarda qué prompt la generó. | Prompts en código. |
| Brief versionado en `metadatos.json`: `propuesto → aprobado/rechazado`; aprobar uno nuevo pasa el anterior a `reemplazado`; solo se edita en `propuesto` | Trazabilidad e inmutabilidad de lo aprobado. | Sobrescribir el brief. |
| Rechazo con `feedback` → nueva versión con la anterior y los comentarios en el contexto (`regenerate`, por defecto `true`) | Iteración guiada por el usuario. | — |
| Ids de referencia inventados por el modelo → `null` + aviso | Integridad de los enlaces brief → referencia. | Confiar en el modelo. |
| `max_output_tokens`: 2.000 (luna), 6.000 (sol) | Ambos razonan por defecto (Paso 6). | Límites ajustados al texto visible. |
| Indexación con concurrencia 3; los fallos por referencia no abortan el resto | Rapidez y robustez. | Secuencial / todo o nada. |
| Respuestas con `cost_eur` y `request_id` de la petición | El usuario ve el coste de cada acción. | Consultar `/costs` aparte. |
| Errores de IA y de pipeline traducidos a HTTP (429, 422, 504, 502, 409...) | Mensajes claros en la UI. | 500 genérico. |
| Máquina de estados genérica en `app/hitl/` (`ensure_transition`) | Reutilizable en el Paso 10. | Lógica dispersa. |
| `ProjectRepository.mutate(project_id, change)` | Leer-modificar-escribir atómico y reutilizable. | Un método por operación. |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `shared/src/shared/models.py` | `ReferenceCategory`, `DimensionsCm`, `ReferenceAnalysis`, `AssetAnalysis`, `Asset.description/analysis`, `FurnitureItem`, `ImagePrompts`, `DesignBriefContent`, `BriefStatus`, `DesignBrief`, `ProjectMetadata.briefs` |
| `backend/app/pipelines/schemas.py` | `strict_schema` |
| `backend/app/pipelines/images.py` | `prepare_image`, `VISION_MIME_TYPES` |
| `backend/app/pipelines/prompts/{__init__.py, context_manager.md, prompt_engineer.md}` | Prompts versionados |
| `backend/app/pipelines/context_manager.py` | `index_references`, `analyze_reference`, `validate_analysis` |
| `backend/app/pipelines/prompt_engineer.py` | `build_context`, `create_brief` |
| `backend/app/pipelines/errors.py` | `PipelineError` (502), `PipelineInputError` (422) |
| `backend/app/hitl/__init__.py`, `backend/app/hitl/briefs.py` | Transiciones; `edit_brief`, `approve_brief`, `reject_brief` |
| `backend/app/api/v1/pipelines.py` | Endpoints de indexación y briefs |
| `backend/app/api/v1/assets.py` | `description` en subidas; `PATCH /assets/{id}` |
| `backend/app/api/errors.py` | Errores de IA, pipelines y HITL → HTTP |
| `backend/app/storage/repository.py` | `mutate`, `read_asset_bytes`, `description` en `add_asset` |
| `backend/app/telemetry/__init__.py` | `request_cost` |
| `backend/Dockerfile` | La comprobación del build carga también los prompts `.md` |
| `postman/interiorai.postman_collection.json` | Carpeta «04 Pipelines (solo mock)» con seguro de costes |
| Tests | `test_pipelines_unit.py` (10), `test_api_pipelines.py` (15) |

## 4. Validación

### Tests y Docker (mock)

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 217 passed (3 ejecuciones) |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| `docker compose build` (con carga de prompts) | ✅ |
| Flujo completo en Docker (mock) con las imágenes del usuario: subida, indexación, brief, aprobación | ✅ |
| Postman CLI (mock) | ✅ 27 peticiones, 48 asserts, 0 fallos |
| Seguro de costes de Postman (copia con `aiMode = azure` simulado) | ✅ Las 6 peticiones de pipelines se omiten (21 enviadas) y el backend no registra llamadas a la IA |

Cubierto por tests: reglas del esquema estricto (y regresión de la propiedad `title`); salida
del mock válida; reducción de imágenes; prompts versionados; indexación (solo referencias,
nota incluida, imagen ≤ 1.024 px, omitir ya analizadas, `force`, fallos por referencia, 422 sin
referencias o con ids ajenos); validación de fichas por el usuario; contexto del brief (solo
capturas/planos como imagen, PDF omitido con aviso, fichas como texto con ids, notas e
indicaciones); ids inventados → `null`; edición, aprobación, bloqueo (409), rechazo con
regeneración (comentarios en el contexto), `reemplazado`; 404; errores de IA → 429 y salida
inválida → 502; telemetría por proyecto con `request_id` y coste por petición.

### Prueba real contra Azure (usuario en modo `azure`, 3 llamadas)

Proyecto real «Salón-cocina-comedor» con la captura de SketchUp del usuario, la captura del
planificador de IKEA y una imagen de inspiración de producto.

| Llamada | Latencia | Tokens entrada / salida / razonamiento | Coste |
|---------|----------|----------------------------------------|-------|
| Ficha del planificador (gpt-6-luna) | 3,9 s | 1.533 / 307 / 124 | 0,000304 € |
| Ficha de inspiración (gpt-6-luna) | 6,2 s | 2.176 / 570 / 345 | 0,000490 € |
| Brief v1 (gpt-6.1-sol) | 41,0 s | 2.639 / 2.018 / 516 | 0,023563 € |
| **Total** | | | **0,024357 €** (estimado 0,02–0,06 €) |

Resultados:
- Planificador: sofá modular JÄTTEBO de IKEA, **285 × 160 × 87 cm leídos de la imagen**.
- Inspiración: **sin medidas (`null`, `desconocido`)**, correctamente; textura «acanalada»
  verde-amarillo oscuro (el usuario puede precisar «pana» al validar la ficha).
- Brief v1: respeta la jerarquía de fuentes (geometría de SketchUp, medidas del planificador,
  inspiración solo para textura y color, **sin copiar la orientación de la inspiración**), enlaza
  el sofá con el id correcto de la ficha, no inventa la altura (deja `null` y pregunta) y genera
  los tres prompts en inglés. Pregunta abierta: si los 87 cm incluyen el reposacabezas.
- El brief v1 queda **propuesto**, pendiente de revisión del usuario (HITL).

Problemas detectados y resueltos durante el paso:
1. **`strict_schema` eliminaba la propiedad `title`** del brief al quitar la palabra clave
   `title` de JSON Schema → corregido antes de llamar a Azure, con test de regresión.
2. Pruebas con `curl` desde Git Bash: las tildes del JSON se envían en cp1252 (400 «error
   parsing the body»). No es un fallo de la API; las pruebas manuales se hacen con un script
   Python (`httpx`) o con Postman.
3. Un comando de limpieza con una variable vacía apuntó a `data/.papelera/*` (estaba vacía).
   Desde entonces se valida el identificador antes de cualquier borrado.

## 5. Estado final

🧪 En validación — rama `feat/paso-08`, Pull Request en GitHub.

## 6. Pendiente / futuro

- B-013: enviar planos PDF al PROMPT_ENGINEER (`input_file` de la Responses API) tras verificarlo en Azure.
- B-014: el brief tarda ~40 s; en la UI (Paso 13) hará falta un indicador de progreso o tareas en segundo plano.
- Revisión del brief v1 real por el usuario (validar fichas, responder la pregunta abierta, aprobar o rechazar).
