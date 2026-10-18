# Paso 15b — Contenedores, papelera y versión 1.0.0

## 1. Objetivo

Cerrar el proyecto: endurecer los contenedores, permitir cualquier usuario en hosts Linux
(B-005), gestionar la papelera desde la línea de comandos (B-007) y publicar la versión 1.0.0
(README final, licencia, changelog, etiqueta y GitHub Release).

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| Endurecimiento común (`x-hardening`): `read_only`, `cap_drop: ALL`, `no-new-privileges`, `pids_limit`, `/tmp` en memoria (256 MB backend, 1 GB frontend para las subidas de Gradio), 2 GB y 2 CPU | Si un componente se ve comprometido, no puede escribir fuera de `data/` y `/tmp`, ni ganar privilegios | Solo usuario sin privilegios (lo que había) |
| `data-init` sigue como root, pero **solo con `CAP_CHOWN`**, sin red y en solo lectura | Es el único que necesita cambiar el propietario de `./data` | Quitarlo (falla en Docker Desktop) |
| **`APP_UID`/`APP_GID`** en `.env` (1000 por defecto) aplicados en tiempo de ejecución (`user:`), con `HOME=/tmp` (B-005) | Sin reconstruir imágenes; probado con el uid 1234 | Argumentos de construcción |
| `./data` se crea a mano (`mkdir -p data`), documentado en el README | El volumen `studio_shared_data` es un bind con nombre (requisito del proyecto) y Docker no crea la carpeta | Bind anónimo |
| **Papelera** (B-007): `python -m app.storage papelera listar / restaurar / vaciar [--dias N] [--si]` | Hasta ahora se gestionaba a mano con riesgo (incidente del Paso 4) | — |
| Vaciar es **definitivo** y pide escribir **VACIAR**; sin terminal exige `--si`; lo que no sigue el formato de la papelera nunca se toca | Datos del usuario (regla 7) | Confirmación con «s» |
| Solo se restauran **proyectos completos** y nunca se sobrescribe uno existente | Un asset borrado ya no figura en `metadatos.json` | Restaurar archivos sueltos |
| **Licencia MIT** (decidida por el usuario) | Permisiva; se puede cambiar para versiones futuras | — |
| Versión **1.0.0** en los cuatro paquetes (la API la lee del paquete) y `CHANGELOG.md` | SemVer: primera versión estable | — |
| README final sin nombres comerciales de modelo (solo roles), con diagramas Mermaid | Regla 2; GitHub los dibuja | Imágenes de diagramas |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `docker-compose.yml` | `x-hardening`, `data-init` mínimo, `APP_UID`/`APP_GID`, `tmpfs`, límites |
| `.env.example` | `APP_UID`, `APP_GID` |
| `backend/app/storage/trash.py` | Lectura, restauración y vaciado de la papelera |
| `backend/app/storage/repository.py`, `__main__.py` | `list_trash`, `restore_project`, `empty_trash`; subcomando `papelera` |
| `backend/tests/test_storage_trash.py` | 5 tests (listar, restaurar, no sobrescribir, vaciar por antigüedad, CLI con confirmación) |
| `pyproject.toml` (×4), `uv.lock` | Versión 1.0.0 |
| `README.md`, `LICENSE`, `CHANGELOG.md` | Versión final |
| `CLAUDE.md`, `docs/agent/fast_api_specs.md` | Comandos y funcionamiento de la papelera |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 338 passed |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| `docker inspect` | ✅ backend y frontend: `1000:1000`, solo lectura, `CapDrop=[ALL]`, `no-new-privileges`, 2 GB, 2 CPU, 256 pids; `data-init`: solo `CAP_CHOWN` |
| newman y Playwright con los contenedores endurecidos | ✅ 47 peticiones / 83 comprobaciones; 5/5; sin errores de permisos en los logs |
| Imágenes con uid 1234, solo lectura y sin capacidades | ✅ el backend crea un proyecto en `data/`; el frontend responde (HTTP 200) |
| `papelera` dentro del contenedor | ✅ lista; sin terminal se niega a vaciar; con `--si` vacía (restos de pruebas, 0,9 MB); el proyecto real, intacto |
| CI en la PR #17 | ✅ `Lint y tests` 53 s · `gitleaks` 6 s · `Docker y extremo a extremo` 3 min 46 s |
| Primera PR de Dependabot (#16) | ⚠️ Proponía Python 3.11 → 3.14 en las imágenes; la CI la rechazó. Dependabot ignora ahora las versiones menor y mayor de la imagen de Python |

## 5. Estado final

🧪 En validación — rama `feat/paso-15b`, Pull Request en GitHub. Tras el merge: etiqueta
`v1.0.0` y GitHub Release.

## 6. Pendiente / futuro

Quedan en el backlog, para cuando haya datos de facturación de Azure (decisión del usuario):
B-008, B-011, B-012, B-015, B-016, B-017, B-020, B-021 y B-022.
