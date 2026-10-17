# Azure AI Foundry — integración por rol

> Estado: **configuración implementada** (Paso 2). Cliente en Paso 6, telemetría en Paso 7.

## Principio

El código solo conoce **roles funcionales**. El despliegue concreto de cada rol se
resuelve en runtime desde variables de entorno. Cambiar de modelo = cambiar `.env`
(y su precio en `config/pricing.yaml`), sin tocar código.

## Superficies de API (API v1 de Azure, sin `api-version`)

| `ApiKind` | Ruta sobre el endpoint | Roles |
|-----------|------------------------|-------|
| `RESPONSES` | `/openai/v1/responses` (Responses API) | Prompt Engineer, Geometric Auditor, Context Manager |
| `IMAGES` | `/openai/v1/images/generations` · `/openai/v1/images/edits` | Fast Draft, Structural Composer |
| `PROVIDER_IMAGES` | `AZURE_FOUNDRY_RENDERER_PATH` (p. ej. `/providers/<proveedor>/v1/<modelo>`) | Photorealistic Renderer |

Con la Responses API, el esfuerzo de razonamiento se envía como `reasoning={"effort": ...}` y
los tokens de razonamiento llegan en `usage.output_tokens_details.reasoning_tokens`.

## Roles

| Rol (enum) | Variable de entorno | Tipo | Uso |
|------------|---------------------|------|-----|
| `PROMPT_ENGINEER` | `DEPLOYMENT_ROLE_PROMPT_ENGINEER` | texto | Notas/planos → prompt técnico estructurado |
| `GEOMETRIC_AUDITOR` | `DEPLOYMENT_ROLE_GEOMETRIC_AUDITOR` | texto + visión | QA del render frente a la captura SketchUp |
| `CONTEXT_MANAGER` | `DEPLOYMENT_ROLE_CONTEXT_MANAGER` | texto + visión | Indexación de referencias y metadatos |
| `FAST_DRAFT` | `DEPLOYMENT_ROLE_FAST_DRAFT` | imagen | Bocetos rápidos, iteración cromática |
| `STRUCTURAL_COMPOSER` | `DEPLOYMENT_ROLE_STRUCTURAL_COMPOSER` | imagen | Encaje de mobiliario respetando cotas |
| `PHOTOREALISTIC_RENDERER` | `DEPLOYMENT_ROLE_PHOTOREALISTIC_RENDERER` | imagen | Render final e inpainting con máscara |

## Configuración

| Variable | Descripción |
|----------|-------------|
| `AI_PROVIDER_MODE` | `mock` (por defecto, sin coste) o `azure` |
| `AZURE_FOUNDRY_ENDPOINT` | **Solo el host** `https://<recurso>.services.ai.azure.com` (se rechaza con ruta) |
| `AZURE_FOUNDRY_API_KEY` | Clave (siempre `SecretStr`, nunca logueada) |
| `AZURE_FOUNDRY_API_VERSION` | Opcional; la API v1 no la usa (verificar renderizador: B-003) |
| `AZURE_FOUNDRY_RENDERER_ENDPOINT` | Opcional: host propio del renderizador (vacío = el principal) |
| `AZURE_FOUNDRY_RENDERER_PATH` | Ruta de la API del renderizador |
| `AZURE_FOUNDRY_TIMEOUT_S`, `AZURE_FOUNDRY_MAX_RETRIES` | Resiliencia |
| `GEOMETRIC_AUDITOR_REASONING_EFFORT` | Por defecto `max` — pendiente de verificar (BACKLOG B-001) |

En modo `azure`, `Settings` exige endpoint, clave, ruta del renderizador y los 6 despliegues.
En modo `mock`, `deployment_for(role)` devuelve `mock-<rol>` si el despliegue no está definido.
Comprobación: `uv run python -m shared`.

## Diseño previsto (Paso 6)

- Interfaz `FoundryClient`: `complete_text(role, ...)`, `generate_image(role, ...)`,
  `edit_image(role, image, mask, ...)`.
- Implementaciones: `AzureFoundryClient` (async) y `MockFoundryClient` (determinista).
- El renderizador fotorrealista usa un adaptador propio (API distinta a la de GPT-image).
- Reintentos con backoff exponencial ante 429/5xx.

## Telemetría (Paso 7, decisión D1)

El interceptor del cliente registra por llamada: `request_id`, `role`, `deployment`,
`input_tokens`, `output_tokens`, `reasoning_tokens`, nº/resolución de imágenes,
`latency_s`, `cost_usd`, `timestamp`. Se persiste en `data/{id}/costes_telemetria.json`.
Precios en `config/pricing.yaml` (decisión D3).
