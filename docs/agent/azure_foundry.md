# Azure AI Foundry — integración por rol

> Estado: **cliente implementado y verificado contra Azure** (Paso 6). Telemetría en el Paso 7.

## Principio

El código solo conoce **roles funcionales**. El despliegue concreto de cada rol se resuelve en
runtime desde variables de entorno (`settings.deployment_for(role)`). Cambiar de modelo =
cambiar `.env` (y su precio en `config/pricing.yaml`), sin tocar código.

## Roles

| Rol (enum) | Variable de entorno | `ApiKind` | Uso |
|------------|---------------------|-----------|-----|
| `PROMPT_ENGINEER` | `DEPLOYMENT_ROLE_PROMPT_ENGINEER` | `RESPONSES` | Notas/planos → prompt técnico |
| `GEOMETRIC_AUDITOR` | `DEPLOYMENT_ROLE_GEOMETRIC_AUDITOR` | `RESPONSES` | QA del render frente a SketchUp (`reasoning.effort`) |
| `CONTEXT_MANAGER` | `DEPLOYMENT_ROLE_CONTEXT_MANAGER` | `RESPONSES` | Indexación de referencias y metadatos |
| `FAST_DRAFT` | `DEPLOYMENT_ROLE_FAST_DRAFT` | `IMAGES` | Bocetos rápidos |
| `STRUCTURAL_COMPOSER` | `DEPLOYMENT_ROLE_STRUCTURAL_COMPOSER` | `IMAGES` | Encaje de mobiliario; **inpainting con máscara** |
| `PHOTOREALISTIC_RENDERER` | `DEPLOYMENT_ROLE_PHOTOREALISTIC_RENDERER` | `PROVIDER_IMAGES` | Render final; edición por **referencias** (sin máscara) |

## Superficies de API

| `ApiKind` | Ruta | Cliente |
|-----------|------|---------|
| `RESPONSES` | `{endpoint}/openai/v1/responses` (sin api-version) | SDK `openai` 3.x |
| `IMAGES` | `{endpoint}/openai/v1/images/{generations,edits}` | SDK `openai` 3.x |
| `PROVIDER_IMAGES` | `{renderer_endpoint}{AZURE_FOUNDRY_RENDERER_PATH}?api-version=preview` | `httpx` |

- Autenticación: `Authorization: Bearer <API key>` en ambos (verificado).
- **El SDK `openai` 3.x usa `httpx2`, una librería distinta de `httpx`**: no compartir clientes.
  `httpx` es dependencia explícita del backend (renderizador).
- Responses API: `store=False`; imágenes como `input_image` (data URL Base64);
  `reasoning={"effort": GEOMETRIC_AUDITOR_REASONING_EFFORT}` **solo** para el auditor;
  salida estructurada con `text.format = {type: json_schema, strict: true}` (esquemas estrictos:
  todas las propiedades en `required` y `additionalProperties: false`).
- Renderizador (API del proveedor): cuerpo `{model: <despliegue>, prompt, width, height,
  output_format, seed?, input_image?, input_image_2..8?}`; respuesta `data[0].b64_json`
  (se aceptan también `data[0].url` y `result.sample`). **Una imagen por petición**; máx. 4 MP;
  15 RPM en el nivel bajo. **No admite máscara** (inpainting → `STRUCTURAL_COMPOSER`).

## Código (`backend/app/foundry/`)

| Módulo | Contenido |
|--------|-----------|
| `types.py` | `TextRequest/TextResult`, `ImageRequest`, `ImageEditRequest` (≤ 8 imágenes + máscara RGBA: transparente = editar), `ImageResult`, `GeneratedImage`, `InputImage`, `Usage` (`reasoning_tokens` incluidos en `output_tokens`) |
| `base.py` | `FoundryClient`: `complete_text`, `generate_image`, `edit_image`, `aclose`; valida rol ↔ operación y máscara en el renderizador (`FoundryUnsupportedError`) |
| `mock.py` | `MockFoundryClient`: texto fijo, JSON por esquema (`sample_from_schema`), PNG con degradado + etiqueta, tokens simulados (≈ caracteres/4; el auditor simula razonamiento) |
| `azure.py` | `AzureFoundryClient`; traducción de errores; reintentos del renderizador con `Retry-After` |
| `errors.py` | `FoundryError` (con `usage` si se facturó), `Auth`, `RateLimit`, `Timeout`, `ContentFilter`, `BadRequest`, `Incomplete`, `Unsupported` |
| `smoke.py` | Verificación real: exige `AI_PROVIDER_MODE=azure` + confirmación `s` por llamada |
| `__init__.py` | `create_foundry_client(settings)` → mock o azure; en la app: `app.state.foundry` / `FoundryDep` |

## Configuración

| Variable | Descripción |
|----------|-------------|
| `AI_PROVIDER_MODE` | `mock` (por defecto, sin coste) o `azure` |
| `AZURE_FOUNDRY_ENDPOINT` | **Solo el host** `https://<recurso>.services.ai.azure.com` |
| `AZURE_FOUNDRY_API_KEY` | Clave (`SecretStr`, nunca logueada) |
| `AZURE_FOUNDRY_API_VERSION` | Opcional; la API v1 no la usa |
| `AZURE_FOUNDRY_RENDERER_ENDPOINT` | Opcional: host propio del renderizador (vacío = el principal) |
| `AZURE_FOUNDRY_RENDERER_PATH` | Ruta de la API del renderizador |
| `AZURE_FOUNDRY_RENDERER_API_VERSION` | `preview` (obligatoria para la API del proveedor) |
| `AZURE_FOUNDRY_TIMEOUT_S`, `AZURE_FOUNDRY_MAX_RETRIES` | Resiliencia |
| `GEOMETRIC_AUDITOR_REASONING_EFFORT` | `max` (verificado, B-001) |

## Comportamiento verificado contra Azure (Paso 6, 2026-10-17)

| Rol | Latencia | Tokens entrada / salida / razonamiento | Observaciones |
|-----|----------|----------------------------------------|---------------|
| PROMPT_ENGINEER | 6,1 s | 44 / 65 / 0 | Sin razonamiento por defecto |
| CONTEXT_MANAGER | 3,9 s | 83 / 64 / 37 | **Razona por defecto**; JSON estricto correcto |
| GEOMETRIC_AUDITOR (`max`) | 23,0 s | 74 / 1.084 / 1.012 | El 93 % de la salida es razonamiento |
| FAST_DRAFT (1024², low) | 14,5 s | 24 / 196 / 0 | PNG |
| STRUCTURAL_COMPOSER (edit + máscara, low) | 18,4 s | 1.053 / 196 / 0 | **La máscara es orientativa**: el objeto puede salirse de la zona |
| PHOTOREALISTIC_RENDERER (1024²) | 34,5 s | — (por imagen) | JPEG; nombre del despliegue tal cual |

Implicaciones: dejar margen en `max_output_tokens` (incluye el razonamiento); el auditor es
lento y con coste dominado por razonamiento; para inpainting exacto, recomponer en local solo
la zona de la máscara (B-009).
