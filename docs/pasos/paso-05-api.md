# Paso 5 — API REST de proyectos y assets

## 1. Objetivo

Exponer por HTTP la capa de almacenamiento, con validación estricta de las subidas, como única
vía de escritura para la interfaz (Pasos 11–14) y para herramientas externas. Incluye una
colección de Postman CLI que recorre el flujo completo contra el contenedor real.

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| **Rutas en inglés** (`/projects`, `/assets`, `/space-types`) (aprobado por el usuario) | Coherencia con los campos JSON en inglés. | `/proyectos` del plan inicial. |
| **Los renders no se pueden subir** (aprobado por el usuario): `{kind}` es `UploadKind` (3 valores) → `render` da 422 y no aparece en Swagger | Los renders solo los genera la IA: histórico y costes trazables. | Permitir importar renders externos. |
| **Pillow + `width_px`/`height_px`** en `Asset` (aprobado por el usuario) | Verificar integridad de imágenes; dimensiones para UI y costes. Compatible con `schema_version: 1` (campos opcionales). | Solo magic bytes. |
| Tipo real por magic bytes; planos admiten PDF | No se confía en extensión ni `Content-Type`. | Validar por extensión. |
| Decodificación completa (`image.load()`) en hilo aparte; límite 80 MP; `DecompressionBombWarning` como error (también en pytest) | Detecta imágenes truncadas y bombas de descompresión; Pillow solo avisa entre 1x y 2x el límite. | `Image.verify()` (no detecta todo). |
| `BodySizeLimitMiddleware` (ASGI puro): `Content-Length` o conteo en streaming; **responde él mismo el 413** y simula una desconexión | Starlette guarda el multipart completo antes del endpoint; FastAPI convierte excepciones al leer el cuerpo en 400 (detectado por un test). | Excepción interna (daba 400). |
| Duplicados por SHA-256 → 409 con `existing_asset_id`; `?allow_duplicate=true` | Cierra B-006. | Duplicados silenciosos. |
| `ProjectUpdate` rechaza `null` en `name`/`space_type` | Un test detectó un 500 en `PATCH {"name": null}`; ahora es 422. | — |
| `clean_original_name`: sin rutas, caracteres de control ni comillas | El nombre va en `Content-Disposition`: evita inyección de cabeceras. | — |
| Descarga con `inline`, RFC 5987 (`filename*=`), `nosniff`, `Cache-Control: private` | Visualización en navegador/Gradio sin que el navegador reinterprete el tipo. | `attachment`. |
| `/space-types` y `/asset-kinds` | La UI obtiene etiquetas y formatos aceptados sin duplicar constantes. | Constantes en el frontend. |
| `backend/tests/conftest.py` como único `conftest.py` del repo | En el modo de importación por defecto de pytest, varios `conftest.py` sin paquete chocarían. | — |
| Colección Postman generada (JSON v2.1) con fixtures en `postman/fixtures/` y `--working-dir postman` | Reproducible; sin secretos (solo `baseUrl`). | — |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `backend/app/api/deps.py` | `SettingsDep`, `RepositoryDep` (movidos desde `main.py`) |
| `backend/app/api/errors.py` | Traducción de errores de dominio a HTTP |
| `backend/app/api/uploads.py` | `UploadKind`, `ACCEPTED_TYPES`, `read_upload`, `decode_base64`, `detect_mime`, `inspect_upload`, `UploadError` |
| `backend/app/api/limits.py` | `BodySizeLimitMiddleware`, `max_body_bytes()` |
| `backend/app/api/v1/{catalog,projects,assets}.py` | Endpoints |
| `backend/app/main.py` | Middleware, handlers y router v1 |
| `backend/app/storage/repository.py` | `get_asset`; `add_asset` con dimensiones; nombre saneado |
| `backend/app/storage/paths.py` | `clean_original_name` |
| `shared/src/shared/models.py` | `Asset.width_px/height_px`, `AssetKind.label`, validación de `null` en `ProjectUpdate` |
| `backend/pyproject.toml` | `pillow`, `python-multipart` |
| `pyproject.toml` | `filterwarnings` de pytest |
| `backend/tests/conftest.py`, `test_api_projects.py` (12), `test_api_assets.py` (24) | Tests |
| `postman/interiorai.postman_collection.json`, `local.postman_environment.json`, `fixtures/plano.png` | Colección |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 121 passed, 0 warnings |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| `postman collection run ... --working-dir postman` contra Docker | ✅ 19 peticiones, 33 asserts, 0 fallos |
| OpenAPI | ✅ 12 endpoints bajo `/api/v1` + `/health` |

Cubierto por tests: ciclo de vida completo de proyectos y assets; multipart, Base64 y data URL;
PNG/JPEG/WebP/PDF; tipo detectado por contenido aunque la extensión mienta; 404, 409, 413
(archivo, Base64, middleware por `Content-Length` y por streaming), 415 (texto disfrazado,
PNG truncado, PDF en referencia), 422 (render, Base64 inválido, archivo vacío, id no UUID,
campos desconocidos, `null`); bomba de descompresión (100 MP en < 100 KB); descarga byte a
byte con cabeceras; nombre de archivo malicioso sin inyección de cabeceras; 500 genérico sin
filtrar contenido ante datos corruptos.

Problemas detectados y resueltos durante el paso:
1. `PATCH {"name": null}` → 500 → validación en `ProjectUpdate` (422).
2. Cuerpo chunked demasiado grande → 400 → el middleware responde el 413 directamente.
3. Heredocs de bash convertían `\x00` en bytes nulos reales al editar código → se editan
   archivos con el editor/scripts, no con heredocs que contengan escapes.

El proyecto que la colección de Postman deja en la papelera se eliminó tras la validación.

## 5. Estado final

🧪 En validación — rama `feat/paso-05`, Pull Request en GitHub.

## 6. Pendiente / futuro

- B-008: actualizar Postman CLI (1.73.0 → 1.75.0) cuando el usuario lo decida.
- Cada ejecución de la colección deja el proyecto borrado en `data/.papelera/` (gestión en B-007).
