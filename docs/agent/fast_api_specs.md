# FastAPI — especificaciones y convenciones

> Estado: **backend completo**: proyectos, assets, costes, pipelines de texto e imagen, auditoría y HITL (Pasos 5 y 7-10).

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
    ├── costes_telemetria.json
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
- CLI: `python -m app.storage {crear,listar,ver,reindexar} [--data-dir DIR]`.

## Endpoints (`/api/v1`, rutas en inglés)

| Método | Ruta | Respuesta | Paso |
|--------|------|-----------|------|
| GET | `/health` | `HealthResponse`; 503 si `data/` no es escribible | 3 ✅ |
| GET | `/space-types` | `[{value, label}]` | 5 ✅ |
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
| GET | `/projects/{id}/costs?limit=50&include_simulated=true` | `CostSummary`: totales, `by_role`, `by_day`, `by_deployment`, `by_project`, últimos registros (con proyecto) y `simulated_excluded` | 7 · 14 ✅ |
| GET | `/costs?limit=50&include_simulated=true` | Igual para **todos los proyectos** (`project_id: null`, desglose `by_project`) | 14 ✅ |
| GET | `/projects/{id}/renders/{render_id}/cost` | `RenderChainCost`: coste acumulado de la cadena que lleva al render (sin simulación; la simulada aparte) | 14 ✅ |
| GET | `/pricing` | `PricingTable` (404 si no hay tabla) | 7 ✅ |
| PATCH | `/projects/{id}/assets/{asset_id}` | `{description}` → `Asset` | 8 ✅ |
| POST | `/projects/{id}/references/index` | `{asset_ids?, force?}` → `{indexed, skipped, failed, cost_eur, request_id}` | 8 ✅ |
| PUT | `/projects/{id}/assets/{asset_id}/analysis` | `ReferenceAnalysis` → `Asset` (ficha `validated`) | 8 ✅ |
| POST | `/projects/{id}/briefs` | `{instructions?}` → 201 `{brief, cost_eur, request_id}` | 8 ✅ |
| GET | `/projects/{id}/briefs` · `/briefs/{brief_id}` | `[DesignBrief]` (versión desc.) · `DesignBrief` | 8 ✅ |
| PATCH | `/projects/{id}/briefs/{brief_id}` | `BriefContentUpdate` (solo `propuesto`; si no, 409) | 8 ✅ |
| POST | `/projects/{id}/briefs/{brief_id}/approve` | `DesignBrief` (el aprobado anterior → `reemplazado`) | 8 ✅ |
| POST | `/projects/{id}/briefs/{brief_id}/reject` | `{feedback, regenerate=true}` → `{rejected, new_brief, cost_eur}` | 8 ✅ |
| POST | `/projects/{id}/renders/drafts` | `{n=2, quality=low, size?, brief_id?, prompt_override?, extra_instructions?}` → 201 `{renders, cost_eur, request_id}` | 9 ✅ |
| POST | `/projects/{id}/renders/compositions` | `{draft_id?, n=1, quality=medium, ...}` (boceto seleccionado) → 201 | 9 ✅ |
| POST | `/projects/{id}/renders/final` | `{composition_id, reference_ids?, n=1, seed?, ...}` (composición seleccionada) → 201 | 9 ✅ |
| GET | `/projects/{id}/renders?stage=` | `[RenderRecord]` (imagen en `/assets/{id}/content`) | 9 ✅ |
| POST | `/projects/{id}/renders/{render_id}/select` · `/discard` | `RenderRecord` | 9 ✅ |
| POST | `/projects/{id}/renders/{render_id}/audit` | `{render, audit, cost_eur, request_id}` (solo composición/final) | 10 ✅ |
| POST | `/projects/{id}/renders/{render_id}/reject` | `{feedback, regenerate=true, apply_audit_suggestions=true}` → `{rejected, new_renders, cost_eur}` | 10 ✅ |
| POST | `/projects/{id}/renders/{render_id}/inpaint` | multipart `mask` (imagen con la proporción del render; lo pintado = zona) + `instruction` [+ `quality`] → 201 `{renders, cost_eur}` (solo composición/final) | 13b ✅ |
| GET | `/projects/{id}/renders/{render_id}/inpaint/{mascara\|bruto\|guia}` | Archivos del retoque: máscara, salida en bruto del modelo y guía del renderizador | 13b ✅ |
| POST | `/projects/{id}/renders/{render_id}/raw` | Salida en bruto de un retoque como imagen nueva de la etapa (sin coste; 409 si ya existe) → 201 `RenderRecord` | 13b ✅ |

## Subidas (`app/api/uploads.py`, `app/api/limits.py`)

- `{kind}` solo admite `UploadKind` (`plano`, `referencia`, `captura_sketchup`): los renders
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
`BriefNotFoundError` → 404 · `TransitionError` → 409 · `PipelineInputError` → 422 ·
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

- `app/pipelines/`: `context_manager.py` (fichas de referencias), `prompt_engineer.py` (brief),
  `schemas.py` (`strict_schema`), `images.py` (`prepare_image`, 1.024 px JPEG),
  `prompts/*.md` (prompts de sistema; `load_prompt(name).version` = hash).
- `app/hitl/`: `ensure_transition` + tablas de transiciones; `briefs.py` (`edit_brief`,
  `approve_brief`, `reject_brief`, `find_brief`). Las transiciones solo las dispara el usuario.
- Los endpoints que llaman a la IA envuelven el trabajo en `telemetry_scope(project_id)` y
  devuelven `cost_eur` (`request_cost`) y `request_id`.
- Escrituras de fichas y briefs con `ProjectRepository.mutate(project_id, change)`.
- Pruebas manuales desde Git Bash: no usar `curl -d` con tildes (cp1252); usar Swagger,
  Postman o un script Python.

## Renders (Paso 9)

- `app/pipelines/renders.py`: el brief debe estar `aprobado` (409); la imagen base es la
  primera captura/plano en imagen del brief; cada etapa exige el render anterior
  `seleccionado` (409) y de la etapa correcta (422).
- Entradas preparadas a ≤ 2.048 px (`INPUT_MAX_SIDE_PX`). Tamaños: GPT-image 1536×1024 /
  1024×1536 / 1024×1024. Render final: por defecto, lado largo 1920 px con la **proporción
  exacta de la captura** (16:9 → 1920×1080); se admite cualquier tamaño ≤ 4 MP. El renderizador
  trabaja en múltiplos de 16 px: se le pide el múltiplo superior (`generation_size`, 1920×1088)
  y se **recorta al centro** al tamaño exacto, sin escalar (`masks.fit`).
- **Un único render final seleccionado**: seleccionar uno descarta el anterior. Bocetos y
  composiciones admiten varios seleccionados (se elige cuál alimenta la etapa siguiente).
- Retoques (`inpaint_render`, Paso 13b): composición con máscara nativa (`STRUCTURAL_COMPOSER`);
  render final regenerando la imagen con una guía (zona en rojo) y la posición en el prompt. Se
  recompone en local solo la zona (`masks.recompose`, borde suavizado hacia fuera) y se guardan
  junto al render `{id}-mascara.png`, `{id}-bruto.png` (salida del modelo) y `{id}-guia.jpeg`
  (`RenderInpaint`). Rechazar un retoque (o su salida en bruto) lo repite con la misma máscara.
- `ProjectRepository.add_render` guarda imagen + `{id}.json` (trazabilidad) en
  `renders_historico/` + asset `render` + `RenderRecord` (id del render = id del asset).
- Transiciones (`RENDER_TRANSITIONS`): `generado → seleccionado | descartado` (reversibles) y
  `→ rechazado` (terminal; la regeneración crea otra imagen con `previous_attempt_id`).
- Formato de salida por etapa en `_STAGE_ROLES` (todo PNG).
- Auditoría (`app/pipelines/auditor.py`): compara con la captura de origen (sigue la cadena de
  renders); a demanda y opcional; historial en `RenderRecord.audits`.
