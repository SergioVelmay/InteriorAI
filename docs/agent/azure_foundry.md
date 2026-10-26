# Azure AI Foundry — integración por rol

> Estado (2.0.0): **cliente verificado contra Azure** (Paso 6) **con telemetría y costes** (Paso 7);
> roles y razonamiento por rol (Paso 18) y especialización de los modelos de imagen (Pasos 22-24).

## Principio

El código solo conoce **roles funcionales**. El despliegue concreto de cada rol se resuelve en
runtime desde variables de entorno (`settings.deployment_for(role)`). Cambiar de modelo =
cambiar `.env` (y su precio en `config/pricing.yaml`), sin tocar código.

## Roles

| Rol (enum) | Variable de entorno | `ApiKind` | Uso |
|------------|---------------------|-----------|-----|
| `PROMPT_ARCHITECT` | `DEPLOYMENT_ROLE_PROMPT_ARCHITECT` | `RESPONSES` | Descripción e imágenes → brief y prompts de imagen (luna: en cada generación, casi gratis) |
| `GEOMETRY_AUDITOR` | `DEPLOYMENT_ROLE_GEOMETRY_AUDITOR` | `RESPONSES` | QA del render frente a SketchUp (`reasoning.effort`) |
| `REFERENCE_ANALYST` | `DEPLOYMENT_ROLE_REFERENCE_ANALYST` | `RESPONSES` | Fichas de las referencias (sol: visión precisa). Antes del Paso 18 se llamaba `CONTEXT_MANAGER` |
| `FAST_DRAFT_MAKER` | `DEPLOYMENT_ROLE_FAST_DRAFT_MAKER` | `IMAGES` | Bocetos rápidos |
| `COMPOSITION_BUILDER` | `DEPLOYMENT_ROLE_COMPOSITION_BUILDER` | `IMAGES` | Encaje de mobiliario; **único rol con máscara** (`MASK_ROLE`, B-037) |
| `REALISTIC_RENDERER` | `DEPLOYMENT_ROLE_REALISTIC_RENDERER` | `PROVIDER_IMAGES` | Render final; edición por **referencias** (sin máscara) |

Nombres desde el Paso 26 (versión 3.0.0, B-057): antes `PROMPT_ENGINEER`, `GEOMETRIC_AUDITOR`,
`FAST_DRAFT`, `STRUCTURAL_COMPOSER` y `PHOTOREALISTIC_RENDERER`. Los datos guardados con un
nombre anterior (telemetría y `RenderRecord.role`) se leen con el actual
(`shared.roles.RENAMED_ROLES`, `current_role`); en el `.env` solo valen los actuales y
`Settings.legacy_env` detecta los anteriores para avisar (registro del backend al arrancar,
`python -m shared` y el error de configuración en modo `azure`).

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
  `reasoning={"effort": GEOMETRY_AUDITOR_REASONING_EFFORT}` **solo** para el auditor;
  salida estructurada con `text.format = {type: json_schema, strict: true}` (esquemas estrictos:
  todas las propiedades en `required` y `additionalProperties: false`).
- Renderizador (API del proveedor): cuerpo `{model: <despliegue>, prompt, width, height,
  output_format, seed?, input_image?, input_image_2..8?}`; respuesta `data[0].b64_json`
  (se aceptan también `data[0].url` y `result.sample`). **Una imagen por petición**; máx. 4 MP;
  15 RPM en el nivel bajo. **No admite máscara** (inpainting → `COMPOSITION_BUILDER`).

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
| `PROMPT_ARCHITECT_REASONING_EFFORT`, `REFERENCE_ANALYST_REASONING_EFFORT` | `medium` por defecto (B-053, Paso 18); `Settings.reasoning_effort(role)` |
| `GEOMETRY_AUDITOR_REASONING_EFFORT` | `medium` (decisión del usuario, Paso 10; `max` también es válido) |
| `GEOMETRY_AUDITOR_TIMEOUT_S` | 900 s (el resto de roles usa `AZURE_FOUNDRY_TIMEOUT_S`) |

## Comportamiento verificado contra Azure (Paso 6, 2026-10-17)

Asignación de entonces: `PROMPT_ARCHITECT` en sol y el antiguo `CONTEXT_MANAGER` en luna (en el
Paso 18 se intercambiaron; ver más abajo).

| Rol | Latencia | Tokens entrada / salida / razonamiento | Observaciones |
|-----|----------|----------------------------------------|---------------|
| PROMPT_ARCHITECT | 6,1 s | 44 / 65 / 0 | Sin razonamiento por defecto |
| REFERENCE_ANALYST | 3,9 s | 83 / 64 / 37 | **Razona por defecto**; JSON estricto correcto |
| GEOMETRY_AUDITOR (`max`) | 23,0 s | 74 / 1.084 / 1.012 | El 93 % de la salida es razonamiento |
| FAST_DRAFT_MAKER (1024², low) | 14,5 s | 24 / 196 / 0 | PNG |
| COMPOSITION_BUILDER (edit + máscara, low) | 18,4 s | 1.053 / 196 / 0 | **La máscara es orientativa**: el objeto puede salirse de la zona |
| REALISTIC_RENDERER (1024²) | 34,5 s | — (por imagen) | JPEG; nombre del despliegue tal cual |

Implicaciones: dejar margen en `max_output_tokens` (incluye el razonamiento); el auditor es
lento y con coste dominado por razonamiento; para inpainting exacto, recomponer en local solo
la zona de la máscara (B-009, resuelto en el Paso 13b).

Retoque del render final (Paso 13b, prueba real): el renderizador **regenera la imagen entera**
y no se limita a la zona aunque se le marque en rojo y en texto (puso la alfombra bajo el
chaise longue); el resto cambia sutilmente (≈ 17 % de píxeles: textura de la pana más blanda,
geometría desplazada). Por eso se guarda también la salida en bruto y el usuario elige. Para
**añadir objetos**, mejor retocar la composición y regenerar el final a partir de ella.
Coste real del retoque 1920×1280 (imagen + guía de 1024 px): 0,0873 €. Desde el Paso 17
(B-038) solo se retocan composiciones, sin recomponer: la imagen es la que devuelve sunburst.

## Verificación del Paso 18 (2026-10-25)

- `reasoning.effort=medium` aceptado por luna y sol. Luna razona en el brief (982 de 1.787
  tokens de salida; 13,5 s; 0,0011 €); sol no razonó ni en la ficha ni en el smoke.
- sunburst **rechaza `input_fidelity`** (400); sin él, el retoque con máscara respeta lo que hay
  fuera de la zona.
- FLUX **acepta `seed` pero no la respeta**: misma semilla y prompt → imágenes distintas
  (parecidas en escena) y la respuesta no devuelve la semilla. No sirve para reproducir versiones.

## Telemetría y costes (Paso 7, `backend/app/telemetry/`)

Contraste con la factura de octubre de 2026 ([docs](../pasos/mantenimiento-2026-10-factura.md)):
los tokens coinciden con la telemetría y el precio en euros es la lista × 0,98463
(`billing_factor`); FLUX factura el MP binario (`megapixel_px: 1048576`) y 1 MP por imagen de
referencia (`reference_mode: per_image`); `gpt-6.1-sol` salió a 0 €, pero se mantiene su precio
de lista a propósito. Un timeout no se facturó.

Renderizador y tamaños (B-020, Paso 16): acepta medidas que no son múltiplo de 16, pero las
**redondea hacia abajo en silencio** (pedida 1920×1080 → devuelta 1920×1072). Por eso se pide el
múltiplo superior y se recorta (`generation_size` + `masks.fit`).

Paso 14: `summary.py` filtra las llamadas simuladas (`include_simulated`; la API las incluye
por defecto, la interfaz no) y agrega todos los proyectos. `chain.py` calcula el coste de la
cadena de un render sumando, por `request_id`, las llamadas de sus renders (lotes completos,
intentos rechazados que sustituye, retoques y su salida en bruto), sus auditorías y el brief
con sus versiones previas (`DesignBrief.request_id`; los briefs anteriores se emparejan por
hora con su llamada de `PROMPT_ARCHITECT`, ±10 s). Sin ramas descartadas ni la indexación de
referencias.

- `app.state.foundry` es un **`MeteredFoundryClient`** que envuelve al cliente mock/Azure
  (`create_metered_client`). Mide latencia (con reintentos), tokens (entrada, caché, escritura
  en caché, texto/imagen, salida, razonamiento), imágenes y megapíxeles, y estima el coste.
- **Para que una llamada se guarde en un proyecto**, envolverla en
  `with telemetry_scope(project_id): ...` (`contextvars`). Sin ámbito, solo se registra en el
  log. El `request_id` lo pone el middleware HTTP.
- Las llamadas fallidas también se registran (`status="error"`), con coste si `FoundryError.usage`.
  Si guardar la telemetría falla, la llamada a la IA no falla (solo se loguea).
- Se registra el **despliegue configurado del rol** (`settings.deployment_for`) incluso en mock,
  para estimar con precios reales; los registros llevan `simulated=true`.
- `config/pricing.yaml` (`pricing.py`): `deployment_type` (`global`), `long_context_threshold_tokens`
  (272.000: entrada > umbral → precio *long*), `megapixel_rounding` (`exact`). Tipos de precio:
  `tokens` (por 1M; entrada sin caché, caché, escritura en caché, salida), `image_tokens` (texto vs
  imagen de entrada, salida) y `megapixels` (primer MP, MP adicionales, MP de referencia).
  Despliegue sin precio → `cost_eur=None` (aviso al arrancar). Montado en solo lectura.
- Persistencia: `ProjectRepository.append_telemetry/read_telemetry` bajo el bloqueo del proyecto.
  Desde el Paso 16, `costes_telemetria.jsonl` (una línea por llamada, solo se añade; B-012); el
  `costes_telemetria.json` anterior se migra solo y se conserva como `.json.migrado`.
- CLI (solo mock): `python -m app.telemetry simular <id> [--llamadas N]`.
- **Coste estimado** con precios de lista: la cifra real está en Azure Cost Management.

## Costes observados en generación de imagen (Paso 9, proyecto real)

| Llamada | Tokens / MP | Coste |
|---------|-------------|-------|
| GPT-image `low` 1536×1024 × 2, editando una captura 1920×1080 | 222 texto + 3.016 imagen entrada; 315 salida | 0,0305 € |
| GPT-image `medium` 1536×1024, 2 imágenes de entrada | 207 texto + 3.044 imagen entrada; 343 salida | 0,0314 € |
| FLUX.2-pro 1920×1280 con 2 referencias | 2,46 MP salida + 3,53 MP referencias | 0,0923 € |

- En GPT-image dominan los **tokens de imagen de entrada**, y no crecen linealmente con el
  número de imágenes (2 imágenes ≈ 1 imagen en este caso).
- En FLUX, las **referencias cuestan tanto como la salida**: reducirlas es la palanca principal (B-015).

## Política de reintentos (Paso 10) — importante para el coste

- **Un timeout NUNCA se reintenta**: Azure pudo completar y facturar el trabajo aunque la
  respuesta no llegue. Incidente: una auditoría `max` con timeout de 120 s se reintentó 3 veces
  (484 s, B-016).
- El SDK `openai` se crea con `max_retries=0`; `_openai_call` reintenta solo **429 y 503**
  (Azure no procesó la petición), hasta `AZURE_FOUNDRY_MAX_RETRIES`, respetando `Retry-After`.
  El renderizador sigue la misma regla.
- El auditor usa `GEOMETRY_AUDITOR_TIMEOUT_S` (`with_options(timeout=...)`).

## Auditoría observada (Paso 10)

`medium`, 2 imágenes ≤ 1.536 px: 43 s, 5.895 tokens de entrada (Azure los informó casi todos como
`cache_write_tokens`, a 11 €/M), 1.875 de salida (506 de razonamiento): **0,147 €**.
