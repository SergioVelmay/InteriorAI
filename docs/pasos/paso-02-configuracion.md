# Paso 2 — Configuración central con Pydantic Settings

## 1. Objetivo

Crear un único punto de configuración, validado y seguro, compartido por backend y frontend,
dentro de un workspace `uv` con Python 3.11.

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| Workspace `uv` en la raíz (`package = false`) con miembro `shared` (paquete `interiorai-shared`, import `shared`, layout `src/`) | Un solo `uv.lock` para todo el repo; backend y frontend se añadirán como miembros en el Paso 3. | Un entorno por servicio sin lock común. |
| Settings por **secciones** (`AppSettings`, `FoundrySettings`, `DeploymentSettings`, `AuditorSettings`, `StorageSettings`, `NetworkSettings`), cada una un `BaseSettings` con su prefijo, agregadas en un `Settings` inmutable | Mantiene los nombres planos del `.env` (`AZURE_FOUNDRY_*`, `DEPLOYMENT_ROLE_*`) sin delimitadores anidados. | Un único `BaseSettings` plano con 25 campos; `env_nested_delimiter` (obliga a `FOUNDRY__ENDPOINT`). |
| Uso de la **API v1 de Azure** (`/openai/v1/...`): `AZURE_FOUNDRY_API_VERSION` pasa a ser opcional | Las URLs de los despliegues del usuario usan `/openai/v1/`, que no requiere `api-version`. | Hacerla obligatoria. |
| `AZURE_FOUNDRY_ENDPOINT` = **solo host**; se rechaza si lleva ruta, query o no es `https` | Evita el error típico de pegar la URL completa del despliegue (`.../openai/v1/responses`). | Aceptar cualquier URL. |
| Nueva `AZURE_FOUNDRY_RENDERER_PATH` | La API del renderizador vive en `/providers/<proveedor>/...` y su ruta contiene el nombre del modelo: no puede ir en código. | Ruta hardcodeada. |
| `AZURE_FOUNDRY_RENDERER_ENDPOINT` opcional, con fallback al endpoint principal | En el recurso del usuario es el mismo host. | — |
| Renombrado `AZURE_REQUEST_TIMEOUT_S` → `AZURE_FOUNDRY_TIMEOUT_S` y `AZURE_MAX_RETRIES` → `AZURE_FOUNDRY_MAX_RETRIES` | Prefijo uniforme de la sección Foundry. | — |
| Sin valores por defecto para despliegues en código; en modo `mock` se usa `mock-<rol>` | Regla crítica: cero nombres comerciales en código. | Defaults con nombres de modelos. |
| Modo `azure` exige endpoint, clave, ruta del renderizador y los 6 despliegues (falla al arrancar con la lista de lo que falta) | Errores de configuración visibles al inicio, no en la primera llamada. | Validación perezosa. |
| `ApiKind` por rol: `RESPONSES`, `IMAGES`, `PROVIDER_IMAGES` | El cliente del Paso 6 elige la superficie de API según el rol, sin conocer el modelo. | — |
| `reasoning_effort` del auditor como texto libre (por defecto `max`), sin lista cerrada | Los valores aceptados están por verificar (B-001); una lista cerrada podría rechazar valores válidos. | `Literal[...]`. |
| CLI `uv run python -m shared` con informe y clave enmascarada (`****abcd`); ante errores muestra solo campo + mensaje, nunca el valor | Validación del `.env` real sin exponer secretos. | — |
| pytest con modo de importación por defecto (no `importlib`) y nombres de archivo de test únicos | Con `importlib`, pytest crea un módulo `shared` vacío a partir de `shared/tests/` que tapa al paquete real. | `--import-mode=importlib`. |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `.python-version` | `3.11` (uv la descarga automáticamente) |
| `pyproject.toml` | Workspace uv, grupo `dev` (pytest, ruff), config de pytest |
| `uv.lock` | Lockfile reproducible |
| `shared/pyproject.toml` | Paquete `interiorai-shared` (pydantic, pydantic-settings) |
| `shared/src/shared/roles.py` | `Role` (6 roles), `ApiKind`, `role.env_var`, `role.api_kind` |
| `shared/src/shared/settings.py` | Secciones de settings, `Settings.load()`, `get_settings()`, `deployment_for()`, `azure_missing()`, informe CLI |
| `shared/src/shared/__main__.py` | Punto de entrada `python -m shared` |
| `shared/tests/test_settings.py` | 29 tests |
| `.env.example` | Variables renombradas, `RENDERER_PATH` añadida, comentarios aclarando host sin ruta |
| `ruff.toml` | `known-first-party = ["shared"]`; ignorar S105/S106 en tests |
| `AGENTS.md`, `CLAUDE.md`, `docs/agent/azure_foundry.md` | Comandos uv, convención de tests, flujo PR, superficies de API |

## 4. Validación

| Prueba | Comando | Resultado |
|--------|---------|-----------|
| Tests | `uv run pytest` | ✅ 29 passed |
| Lint / formato | `uv run ruff check .` · `uv run ruff format --check .` | ✅ |
| `.env` real del usuario | `uv run python -m shared` | ✅ Carga en modo `mock`; endpoint y 6 despliegues OK; para modo `azure` solo falta `AZURE_FOUNDRY_RENDERER_PATH` |

Cobertura de los tests: valores por defecto en modo mock, carga desde `.env`, prioridad de
variables de proceso sobre `.env`, valores vacíos tratados como no definidos, modo azure
incompleto/completo, endpoint con ruta/query/no-https rechazado, normalización de barra final,
fallback del renderizador, validación de la ruta del renderizador, la clave nunca aparece en
`str`/`repr`/`model_dump`/`model_dump_json`/informe/errores, resolución de cada rol, nombres
`mock-*`, todos los roles tienen `ApiKind`, inmutabilidad.

## 5. Estado final

✅ Cerrado — rama `feat/paso-02`, PR #1 aprobada por el usuario y mergeada a `main`.

## 6. Publicación del repositorio (entre Paso 1 y Paso 2)

- Repositorio público: https://github.com/SergioVelmay/InteriorAI (rama por defecto `main`).
- Antes de publicar: gitleaks sobre todo el historial (sin fugas), `.env` nunca versionado,
  autoría de los commits reescrita al email noreply de GitHub (configurado solo en este repo).
- GitHub: *secret scanning* y *push protection* activos.
- Flujo acordado: una Pull Request por paso; el usuario valida en el PR y después se hace merge.

## 7. Pendiente / futuro

- B-003: verificar si la API del renderizador requiere `api-version` (Paso 6).
- Activar Dependabot (Paso 15).
