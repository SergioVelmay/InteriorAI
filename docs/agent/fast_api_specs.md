# FastAPI — especificaciones y convenciones

> Estado: **almacenamiento implementado** (Paso 4). Se completa en los Pasos 5 y 7.

## Estructura y arranque

- App factory: `backend/app/main.py::create_app(settings=None)`; uvicorn con
  `--factory app.main:create_app`. Sin instancia global (los tests inyectan `Settings`).
- `Settings` vive en `app.state.settings`; en endpoints se obtiene con la dependencia
  `SettingsDep` (`get_app_settings`).
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
  `get`, `update`, `delete` (→ `.papelera/{id}-{ts}`), `add_asset`, `list_assets`, `asset_path`,
  `remove_asset` (→ `.papelera/{id}/`), `reindex`.
- Errores: `ProjectNotFoundError`, `AssetNotFoundError`, `InvalidPathError`, `CorruptDataError`.
- Escritura atómica (`atomic.py`: temp + fsync + `replace_with_retry`, que reintenta `os.replace`
  ante `PermissionError` de Windows) bajo `LockManager.hold(key)`
  (`asyncio.Lock` + `filelock`). **Orden de locks: proyecto → índice.** E/S en `anyio.to_thread`.
- `metadatos.json` se escribe el último al crear: su presencia marca el proyecto como completo.
- En disco los assets se guardan como `{uuid}.{ext}`; el nombre original solo en metadatos.
- CLI: `python -m app.storage {crear,listar,ver,reindexar} [--data-dir DIR]`.

## Endpoints previstos

| Método | Ruta | Paso |
|--------|------|------|
| GET | `/health` | 3 ✅ |
| POST/GET | `/api/v1/proyectos` | 5 |
| GET/PATCH/DELETE | `/api/v1/proyectos/{id}` | 5 |
| POST/GET | `/api/v1/proyectos/{id}/assets/{tipo}` | 5 |
| GET | `/api/v1/proyectos/{id}/costes` | 7 |
| POST | `/api/v1/proyectos/{id}/pipelines/...` | 8–9 |
| POST | `/api/v1/proyectos/{id}/iteraciones/{it}/{aprobar\|rechazar}` | 10 |

Uploads: multipart y Base64, límite `MAX_UPLOAD_MB`, validación de MIME.
