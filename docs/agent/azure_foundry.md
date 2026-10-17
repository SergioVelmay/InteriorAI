# Azure AI Foundry — integración por rol

> Estado: **diseño** (Paso 1). Se completa en los Pasos 6 (cliente) y 7 (telemetría).

## Principio

El código solo conoce **roles funcionales**. El despliegue concreto de cada rol se
resuelve en runtime desde variables de entorno. Cambiar de modelo = cambiar `.env`
(y su precio en `config/pricing.yaml`), sin tocar código.

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
| `AZURE_FOUNDRY_ENDPOINT` | Endpoint del recurso Foundry |
| `AZURE_FOUNDRY_API_KEY` | Clave (siempre `SecretStr`, nunca logueada) |
| `AZURE_FOUNDRY_API_VERSION` | Versión de API |
| `AZURE_FOUNDRY_RENDERER_ENDPOINT` | Opcional: endpoint propio del renderizador si difiere |
| `AZURE_REQUEST_TIMEOUT_S`, `AZURE_MAX_RETRIES` | Resiliencia |
| `GEOMETRIC_AUDITOR_REASONING_EFFORT` | Por defecto `max` — pendiente de verificar (BACKLOG B-001) |

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
