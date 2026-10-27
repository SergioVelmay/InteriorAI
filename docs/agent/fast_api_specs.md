# FastAPI — especificaciones y convenciones

> Estado (4.0.0, en curso): **backend completo**: proyectos, referencias con receta y ficha, costes, prompt automático, bocetos, composición (auditoría y retoque) y render final (Pasos 5-10 y 17-24). Esquema v3 sin la v1 (Paso 33), con migración automática.

## Estructura y arranque

- App factory: `backend/app/main.py::create_app(settings=None)`; uvicorn con
  `--factory app.main:create_app`. Sin instancia global (los tests inyectan `Settings`).
- `Settings` y `ProjectRepository` viven en `app.state`; en endpoints se obtienen con
  `SettingsDep` / `RepositoryDep` (`app/api/deps.py`).
- El `lifespan` configura logging, crea `DATA_DIR` y registra un resumen sin secretos.
- `GET /health` → `{"status": "ok"|"degraded", "version", "mode", "data_dir_writable"}`;
  `503` si el volumen no es escribible (lo usa el `HEALTHCHECK` de Docker).
- Tests: `TestClient(create_app(Settings.load(env_file=None)))` con `DATA_DIR` en `tmp_path`.

## Convenciones

- Prefijo de versión: `/api/v1`. Healthcheck sin prefijo: `GET /health`.
- Async en todos los endpoints; I/O de disco con `anyio`/`aiofiles` o en threadpool.
- Errores con `HTTPException` y cuerpo `{"detail": ...}`; `404` recurso inexistente,
  `409` transición HITL no permitida, `413` payload demasiado grande, `422` validación.
- Cada petición recibe un `X-Request-ID` (middleware) que se propaga a la telemetría.
- El backend es el **único escritor** de `data/`.

## Almacenamiento (Paso 4) — `backend/app/storage/`

```
data/
├── proyectos.json                    # índice global (derivable: se repara solo al arrancar)
├── .papelera/                        # borrado suave de proyectos y assets
├── .locks/                           # filelocks (index.lock, {uuid}.lock)
└── {id_proyecto}/                    # id = UUID (protección path traversal)
    ├── metadatos.json
    ├── costes_telemetria.jsonl       # una línea por llamada a la IA (Paso 16)
    ├── planos/
    ├── referencias/
    ├── capturas_sketchup/
    └── renders_historico/            # cada render: imagen + JSON sidecar
```

- Modelos en `shared/models.py`: `SpaceType`, `AssetKind` (`.folder`), `Asset`, `ProjectCreate`,
  `ProjectUpdate` (`changes()` = campos enviados), `ProjectSummary`, `ProjectMetadata`,
  `ProjectIndex`, `TelemetryLog`. Campos en inglés, valores y carpetas en español,
  `schema_version: 1` en cada JSON, `extra="forbid"`.
- `ProjectRepository(data_dir)` (dependencia `RepositoryDep`): `init`, `list_projects`, `create`,
  `get`, `update`, `delete` (→ `.papelera/{id}-{ts}`), `add_asset`, `list_assets`, `get_asset`, `asset_path`,
  `remove_asset` (→ `.papelera/{id}/`), `reindex`.
- Errores: `ProjectNotFoundError`, `AssetNotFoundError`, `InvalidPathError`, `CorruptDataError`.
- Escritura atómica (`atomic.py`: temp + fsync + `replace_with_retry`, que reintenta `os.replace`
  ante `PermissionError` de Windows) bajo `LockManager.hold(key)`
  (`asyncio.Lock` + `filelock`). **Orden de locks: proyecto → índice.** E/S en `anyio.to_thread`.
- `metadatos.json` se escribe el último al crear: su presencia marca el proyecto como completo.
- En disco los assets se guardan como `{uuid}.{ext}`; el nombre original solo en metadatos.
- CLI: `python -m app.storage {crear,listar,ver,reindexar} [--data-dir DIR]` (`crear` admite
  `--descripcion`).

## Endpoints (`/api/v1`, rutas en inglés)

| Método | Ruta | Respuesta | Paso |
|--------|------|-----------|------|
| GET | `/health` | `HealthResponse`; 503 si `data/` no es escribible | 3 ✅ |
| GET | `/asset-kinds` | `[{value, label, folder, uploadable, accepted_mime_types}]` | 5 ✅ |
| POST | `/projects` | 201 `ProjectMetadata` + `Location` | 5 ✅ |
| GET | `/projects` | `[ProjectSummary]` (más reciente primero) | 5 ✅ |
| GET/PATCH | `/projects/{id}` | `ProjectMetadata` | 5 ✅ |
| DELETE | `/projects/{id}` | 204 (borrado suave) | 5 ✅ |
| POST | `/projects/{id}/assets/{kind}` | multipart `file` → 201 `Asset` | 5 ✅ |
| POST | `/projects/{id}/assets/{kind}/base64` | `{filename, data_base64}` → 201 `Asset` | 5 ✅ |
| GET | `/projects/{id}/assets?kind=` | `[Asset]` | 5 ✅ |
| GET/DELETE | `/projects/{id}/assets/{asset_id}` | `Asset` / 204 (borrado suave) | 5 ✅ |
| GET | `/projects/{id}/assets/{asset_id}/content` | archivo (`inline`, `nosniff`) | 5 ✅ |
| GET | `/projects/{id}/costs?limit=50&include_simulated=true` | `CostSummary`: totales, `by_role` (rol actual, `label` = su despliegue actual), `by_day`, `by_deployment`, `by_project`, `by_day_role` y `by_project_role` (para apilar), `role_deployments` (despliegue actual de cada rol), últimos registros (con proyecto y `call_role`) y `simulated_excluded`. Cada llamada cuenta en el rol que **hoy** tiene su despliegue (Paso 26) | 7 · 14 · 26 ✅ |
| GET | `/costs?limit=50&include_simulated=true` | Igual para **todos los proyectos** (`project_id: null`, desglose `by_project`) | 14 ✅ |
| GET | `/costs/alerts` | `CostAlerts`: gasto real (sin simulación) por proyecto y total frente a `COST_ALERT_PROJECT_EUR` / `COST_ALERT_TOTAL_EUR`; solo informa | 16 ✅ |
| GET | `/projects/{id}/renders/{render_id}/cost` | `RenderChainCost`: coste acumulado de la cadena que lleva al render (sin simulación; la simulada aparte) | 14 ✅ |
| GET | `/pricing` | `PricingTable` (404 si no hay tabla) | 7 ✅ |
| PATCH | `/projects/{id}/assets/{asset_id}` | `{description}` → `Asset` | 8 ✅ |
| POST | `/projects/{id}/references/index` | `{asset_ids?, force?}` → `{indexed, skipped, failed, cost_eur, request_id}`: análisis en bloque de las referencias sin receta | 8 · 21 ✅ |
| POST | `/projects/{id}/assets/{asset_id}/analyze` | `{notes?}` → `{asset, cost_eur, request_id}`: receta de una referencia (al subirla o de nuevo con otras notas); la ficha se guarda con lo que piden las notas marcado | 21 ✅ |
| PUT | `/projects/{id}/assets/{asset_id}/sheet` | `{selected: ["grupo:índice"]}` → `Asset`: «Guardar ficha» (vacía = referencia descartada) | 21 ✅ |
| POST | `/projects/{id}/renders/drafts` | `{n=4 (1-8), quality=medium, size=1536x1024, prompt_override?, extra_instructions?}` → 201 `{renders, cost_eur, request_id}`: referencias activas y prompt automático (`prompt_info`), sin brief | 9 · 22 ✅ |
| POST | `/projects/{id}/renders/compositions` | `{draft_id?, source=boceto\|composicion, use_audit=false, audit_notes, n=1, quality=medium, size=1536x1024, ...}` (parte del boceto o de la composición seleccionados; apoyos hasta 12) → 201 | 9 · 23 ✅ |
| POST | `/projects/{id}/renders/final` | `{composition_id?, source=composicion\|render_final, variant_of?, size=2448x1632, extra_instructions, n=1}` (solo la imagen de partida y el prompt; `variant_of`: «Otra versión», repite prompt, partida y tamaño) → 201 | 9 · 24 ✅ |
| GET | `/projects/{id}/renders?stage=` | `[RenderRecord]` (imagen en `/assets/{id}/content`) | 9 ✅ |
| POST | `/projects/{id}/renders/{render_id}/select` | `RenderRecord` (la seleccionada antes en la etapa vuelve a `generado`) | 9 · 17 ✅ |
| POST | `/projects/{id}/renders/{render_id}/audit` | `{notes?}` → `{render, audit, cost_eur, request_id}` (boceto, composición o final; las imágenes nuevas, frente a todas las referencias del espacio) | 10 · 23 ✅ |
| POST | `/projects/{id}/renders/{render_id}/inpaint` | multipart `mask` (imagen con la proporción del render; lo pintado = zona) + `instruction` [+ `quality`, `extra_instructions`, `use_audit`, `audit_notes`] → 201 `{renders, cost_eur}` (solo composiciones, B-038; prompt del PROMPT_ARCHITECT, Paso 23) | 13b · 17 ✅ |
| GET | `/projects/{id}/renders/{render_id}/inpaint/mascara` | Máscara del retoque (los archivos bruto/guía de la v1 quedan en disco) | 13b · 17 ✅ |

## Subidas (`app/api/uploads.py`, `app/api/limits.py`)

- `{kind}` solo admite `UploadKind` (`referencia`, desde el esquema 2, B-028): los renders
  solo los genera la IA (otro valor → 422).
- Tipo real por magic bytes (`detect_mime`), nunca por extensión/`Content-Type`. Todos los tipos
  (planos incluidos, desde el Paso 12): PNG, JPEG, WebP → si no, 415.
- Imágenes decodificadas por completo con Pillow (corruptas → 415) y límite de 80 MP
  (`DecompressionBombWarning` convertido en error → 413). Se guardan `width_px`/`height_px`.
- Tamaño: `MAX_UPLOAD_MB` por archivo (multipart por bloques; Base64 estimado antes de
  decodificar) → 413. `BodySizeLimitMiddleware` corta cualquier cuerpo > 4/3·límite + 1 MiB
  (por `Content-Length` o contando bytes si es chunked) **respondiendo él mismo el 413**
  (FastAPI convertiría una excepción al leer el cuerpo en un 400).
- Duplicados por `sha256` en el proyecto → 409 `{"detail", "existing_asset_id"}`;
  `?allow_duplicate=true` para forzar.
- `original_name` saneado (`clean_original_name`: sin rutas, controles ni comillas).

## Middleware (orden: el último añadido es el más externo)

1. `RequestIdMiddleware` (externo): `X-Request-ID` (respeta el del cliente si cumple
   `^[A-Za-z0-9._-]{1,64}$`; si no, `uuid4().hex`), lo devuelve en la respuesta, lo pone en el
   `contextvar` de telemetría y registra método, ruta, estado y latencia.
2. `BodySizeLimitMiddleware`.

## Errores (`app/api/errors.py`)

`ProjectNotFoundError`/`AssetNotFoundError` → 404 · `InvalidPathError` → 422 ·
`CorruptDataError` → 500 genérico (detalle solo en logs) · `UploadError` → su código ·
`TransitionError` → 409 · `PipelineInputError` → 422 ·
`PipelineError` → 502 · `FoundryUnsupportedError` → 400 · `FoundryContentFilterError` → 422 ·
`FoundryRateLimitError` → 429 · `FoundryTimeoutError` → 504 · otros `FoundryError` → 502.
Formato siempre `{"detail": "<mensaje en español>"}`.

## Notas de FastAPI 0.143

Los routers anidados no se aplanan en `app.routes` (aparecen como entradas agrupadas sin
`methods`); para inspeccionar rutas usar `/openapi.json`.

## Tests

`backend/tests/conftest.py`: `clean_env` (autouse), `make_api(max_upload_mb=None)`, `api`,
`image_bytes()`. Es el único `conftest.py` del repo (pytest en modo de importación por defecto).

## Pipelines y HITL (Paso 8)

- `app/pipelines/`: `reference_analyst.py` (recetas y fichas de las referencias, Paso 21), `sources.py` (reglas de las referencias activas, `shared.supports`), `prompt_writer.py` (prompt automático),
  `schemas.py` (`strict_schema`), `images.py` (`prepare_image`, 1.024 px JPEG),
  `prompts/*.md` (prompts de sistema; `load_prompt(name).version` = hash).
- `app/hitl/`: `ensure_transition` + tablas de transiciones. Las transiciones solo las dispara
  el usuario.
- Los endpoints que llaman a la IA envuelven el trabajo en `telemetry_scope(project_id)` y
  devuelven `cost_eur` (`request_cost`) y `request_id`.
- Escrituras de fichas con `ProjectRepository.mutate(project_id, change)`.
- Pruebas manuales desde Git Bash: no usar `curl -d` con tildes (cp1252); usar Swagger,
  Postman o un script Python.

## Papelera (Paso 15b)

`app/storage/trash.py` + `ProjectRepository.list_trash/restore_project/empty_trash` (bloqueo
`papelera`). Proyecto borrado: `.papelera/{id}-{marca}`; asset borrado:
`.papelera/{id}/{marca}-{archivo}`. Solo se restauran proyectos completos (nunca se
sobrescribe uno existente); vaciar es definitivo, admite `--dias N` y la CLI pide escribir
VACIAR (o `--si`). Lo que no sigue esos formatos nunca se toca.

## Renders (Paso 9)

- `app/pipelines/renders.py`: bocetos a partir de las referencias activas; cada etapa exige
  el render anterior `seleccionado` (409) y de la etapa correcta (422).
- Entradas preparadas a ≤ 2.048 px (`INPUT_MAX_SIDE_PX`). Tamaños: GPT-image 1536×1024 /
  1024×1536 / 1024×1024. Render final (Paso 24): 3:2 a 2448×1632 por defecto y tres
  resoluciones por proporción en `shared/sizes.py`; se admite cualquier tamaño ≤ 4 MP. El
  renderizador
  trabaja en múltiplos de 16 px: se le pide el múltiplo superior (`generation_size`, 1920×1088)
  y se **recorta al centro** al tamaño exacto, sin escalar (`masks.fit`).
- **Una sola imagen seleccionada por etapa** (B-043): seleccionar otra devuelve la anterior a
  `generado`.
- Retoques (`inpaint_render`, Paso 13b · B-038): solo composiciones, con máscara nativa
  (`COMPOSITION_BUILDER`) y la posición de la zona en el prompt; se guarda la imagen completa
  del modelo (sin recomponer) y `{id}-mascara.png` (`RenderInpaint`).
- `ProjectRepository.add_render` guarda imagen + `{id}.json` (trazabilidad) en
  `renders_historico/` + asset `render` + `RenderRecord` (id del render = id del asset).
- Transiciones (`RENDER_TRANSITIONS`): `generado → seleccionado` (acción del usuario) y
  `seleccionado → generado` (al seleccionar otra de la etapa). Sin rechazos ni descartes (B-048).
- Esquema de `metadatos.json` (`SCHEMA_VERSION = 3`, Paso 33): la v2 se migra sola
  (`app/storage/migrations.py`) al arrancar y al restaurar de la papelera, con copia previa en
  `metadatos.v2.json`; las imágenes de la v1 quedan sueltas (sin brief, rechazos, salidas en
  bruto ni sus retoques). Los datos de la 1.0.0 (esquema 1) ya no se leen: se actualizan antes
  con la 3.0.0. El índice `proyectos.json` sigue en el esquema 2.
- Formato de salida por etapa en `_STAGE_ROLES` (todo PNG).
- Auditoría (`app/pipelines/auditor.py`): a demanda y opcional; historial en
  `RenderRecord.audits`. Desde el Paso 23 (B-046) audita sobre todo el boceto seleccionado,
  frente a todas las referencias activas con perspectiva o geometría (`reference_asset_ids`,
  prompt `auditor_espacio`) y con las observaciones del usuario (`notes`); las imágenes de la v1
  se comparan con su captura de origen (`reference_asset_id`, siguiendo la cadena de renders).
- Contexto del PROMPT_ARCHITECT (`prompt_writer.references_section`): de cada referencia, lo
  marcado (`seleccion`) y, de las que se envían como imagen, lo no marcado (`ignorar`), para que
  el prompt diga qué no tomar (Paso 28, B-068).
- Qué recibe cada generación (`shared/supports.py`, compartido con la interfaz): la imagen de
  partida (base con perspectiva en los bocetos; boceto o composición seleccionados en la
  composición) y hasta `MAX_SUPPORTS = 12` apoyos, primero los del espacio y después por
  antigüedad (`split_supports`).
