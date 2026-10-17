# Paso 4 — Modelo de dominio y capa de almacenamiento

## 1. Objetivo

Modelar los "Proyectos" (un espacio de la casa cada uno) y persistirlos en `DATA_DIR` de forma
segura: escritura atómica, concurrencia controlada, sin path traversal y con un índice global
que se repara solo.

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| **Campos JSON en inglés**; valores de enums, nombres de archivos/carpetas y textos de UI en español (aprobado por el usuario) | Coherencia con la regla "identificadores en inglés" de `AGENTS.md`, respetando los nombres pedidos (`metadatos.json`, `planos/`…). | Campos en español. |
| **Borrado suave** de proyectos (`.papelera/{id}-{ts}`) y assets (`.papelera/{id}/{ts}-{archivo}`) (aprobado por el usuario) | Regla 7: no se borran datos del usuario sin confirmación; recuperable a mano. | Borrado definitivo. |
| Modelos en `shared/models.py` | Los usan el backend (escritura) y el frontend (lectura directa del volumen, respuestas de la API). | Modelos solo en el backend. |
| `schema_version: 1` en cada JSON y `extra="forbid"` | Permite migraciones futuras; rechaza campos desconocidos. | — |
| `metadatos.json` contiene los assets del proyecto; el índice solo un resumen | Una única fuente de verdad por proyecto; el índice es derivable. | Índice con todos los datos. |
| Bloqueos en dos niveles: `asyncio.Lock` + `filelock` (`thread_local=False`), orden proyecto → índice | Concurrencia en el proceso y entre procesos (CLI, futuros workers). El `filelock` se adquiere en un hilo del pool y se libera en otro. | Solo `asyncio.Lock`. |
| Toda la E/S en `anyio.to_thread` | No bloquear el event loop de FastAPI. | E/S síncrona en corrutinas. |
| `metadatos.json` se escribe en último lugar al crear | Su presencia marca el proyecto como completo; carpetas a medias no se indexan. | — |
| **El índice se repara solo al arrancar** si no existe, está corrupto o no coincide con las carpetas | Es derivable de los `metadatos.json`; evita que un fallo deje la app inutilizable. | Fallar al arrancar. |
| Assets guardados como `{uuid}.{ext}` (extensión solo si es alfanumérica, ≤ 8 caracteres; si no, `.bin`) | El nombre del usuario nunca toca el disco; el original se guarda en metadatos. | Sanear el nombre original. |
| SHA-256 de cada asset | Base para detectar duplicados (B-006). | — |
| `os.replace` con **reintentos ante `PermissionError`** (10 intentos, espera creciente, máx. ~0,5 s) | En Windows, el antivirus o el indexador abren un instante los archivos recién escritos y `os.replace` falla con *Access denied*. Afecta también a Docker Desktop, porque `./data` vive en disco de Windows. | Ignorarlo (test intermitente, 1 de cada ~11 ejecuciones). |
| Método `list_projects` (no `list`) | No ocultar el `list` de Python dentro de la clase. | — |
| CLI `python -m app.storage` (`crear`, `listar`, `ver`, `reindexar`) | Validación del paso sin API y mantenimiento futuro. | — |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `shared/src/shared/models.py` | `SpaceType` (+ `label`), `AssetKind` (+ `folder`), `Dimensions`, `Asset`, `ProjectCreate`, `ProjectUpdate`, `ProjectSummary`, `ProjectMetadata`, `ProjectIndex`, `TelemetryLog` |
| `backend/app/storage/paths.py` | Constantes de archivos, `parse_uuid`, `safe_join`, `stored_asset_name`, `ProjectPaths` |
| `backend/app/storage/atomic.py` | `write_bytes_atomic`, `write_json_atomic`, `read_json`, `CorruptDataError` |
| `backend/app/storage/locks.py` | `LockManager.hold(key)` |
| `backend/app/storage/repository.py` | `ProjectRepository` y errores de dominio |
| `backend/app/storage/__main__.py` | CLI |
| `backend/app/main.py` | `ProjectRepository` en `app.state`, `init()` en el arranque, `RepositoryDep` |
| `backend/pyproject.toml` | `anyio`, `filelock` |
| Tests | `shared/tests/test_models.py` (7), `backend/tests/test_storage_paths_atomic.py` (23), `backend/tests/test_storage_repository.py` (16) |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 85 passed; **25 ejecuciones seguidas sin fallos** |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Estructura al crear (4 subcarpetas, `metadatos.json`, `costes_telemetria.json`, índice) | ✅ test + Docker |
| CRUD, orden por `updated_at`, rechazo de `name=None` en update | ✅ |
| Borrado suave de proyectos y assets | ✅ |
| Path traversal en ids, rutas y nombres de archivo | ✅ rechazados |
| Fallo simulado de `os.replace`: original intacto y sin temporales | ✅ |
| JSON corrupto / esquema inválido / vacío → `CorruptDataError` | ✅ |
| 50 creaciones concurrentes → índice con 50 entradas | ✅ |
| 30 assets concurrentes desde 2 repositorios (simula 2 procesos) → 30 assets | ✅ |
| `reindex`, reparación al arrancar (desincronizado, corrupto, inexistente), proyectos corruptos omitidos | ✅ |
| Docker: `python -m app.storage crear/listar` → aparece en `./data` del host | ✅ |
| Docker: el frontend lee `proyectos.json` del volumen (solo lectura) | ✅ |
| Docker: índice vaciado a mano o corrupto + reinicio del backend → reparado (log `WARNING`) | ✅ |
| Docker: `ver ../../etc/passwd` | ✅ `Identificador no válido`, exit 1 |

Mejoras surgidas durante la validación:
1. En un `DATA_DIR` vacío no se creaba `proyectos.json` → el arranque lo crea siempre.
2. Un `proyectos.json` corrupto habría impedido operar → se reconstruye al arrancar.
3. Test intermitente en Windows (`test_concurrent_assets_from_two_repositories`, 1 fallo cada
   ~11 ejecuciones): `PermissionError` en `os.replace` porque un proceso externo
   (antivirus/indexador) abría el archivo destino → `replace_with_retry` con 2 tests nuevos.

El proyecto de prueba creado en `./data` durante la validación se eliminó al terminar.

## 5. Estado final

✅ Cerrado — rama `feat/paso-04`, PR #3 revisada y mergeada por el usuario.

## 6. Pendiente / futuro

- B-006: aviso de assets duplicados por `sha256` (Paso 5).
- B-007: comando para listar/restaurar/vaciar la papelera, siempre con confirmación (Paso 15).
