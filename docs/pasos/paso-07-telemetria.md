# Paso 7 — Telemetría y control de costes

## 1. Objetivo

Registrar cada llamada a la IA en el `costes_telemetria.json` de su proyecto (tokens de
entrada, caché, salida y razonamiento; latencia; imágenes y megapíxeles; coste estimado en EUR)
y exponer un resumen agregado para el dashboard de Gradio (Paso 14).

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| Precios de lista del usuario en `config/pricing.yaml`, indexados por nombre de despliegue | Decisión D3; cambiar de modelo = `.env` + YAML. | Precios en código. |
| **Los 6 despliegues son Global Standard** → `deployment_type: global` (usuario) | Los precios Data Zone son ~20 % más caros. | Data Zone. |
| **Umbral de contexto largo: 272.000 tokens de entrada** (usuario) | Criterio de Azure para GPT-6/GPT-6.1. | Umbral vacío. |
| **Megapíxeles exactos** (`w·h/1e6`), configurable a `ceil` (usuario) | Pendiente de contrastar con la factura (B-011). | Redondeo al MP completo. |
| FLUX: primer MP de cada imagen a `initial_mp`, el resto a `additional_mp`, referencias a `reference_mp` | Interpretación de la tabla de precios del usuario. | — |
| `cache_write_tokens` sí se tarifican | La Responses API los informa en `usage.input_tokens_details` (descubierto al implementar; la propuesta decía lo contrario). | Ignorarlos. |
| Desglose `input_text_tokens` / `input_image_tokens` para GPT-image | Se cobran distinto (4,40 € frente a 7,04 € por 1M). | Toda la entrada como texto. |
| `MeteredFoundryClient` envuelve al cliente (patrón decorador) | Los pipelines no cambian; mock y Azure se miden igual. | Telemetría dentro de cada cliente. |
| Contexto por `contextvars`: `telemetry_scope(project_id)` y `request_id` del middleware | Sin pasar parámetros por todas las capas; aislado por tarea asíncrona. | Parámetro explícito en cada llamada. |
| Se registra el **despliegue configurado del rol** también en mock (`simulated=true`) | El dashboard se puede desarrollar con costes realistas sin gastar. | Registrar `mock-<rol>` (sin precio). |
| Llamadas fallidas registradas, con coste si el error trae `usage` | Azure factura las respuestas incompletas. | Registrar solo los aciertos. |
| Un fallo al guardar la telemetría no rompe la llamada a la IA | La imagen o el texto ya se han pagado; solo se loguea. | Propagar el error. |
| `RequestIdMiddleware` como middleware más externo | El `X-Request-ID` aparece también en respuestas 413 y de error. | — |
| `config/` copiado en la imagen **y** montado en solo lectura | Precios editables sin reconstruir (`docker compose watch` reinicia el backend). | Solo en la imagen. |
| CLI `python -m app.telemetry simular` bloqueado fuera de mock | Validar el paso sin pipelines y sin coste. | Endpoint de depuración. |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `config/pricing.yaml` | Precios de los 6 despliegues (texto, imagen por tokens, megapíxeles) |
| `backend/app/telemetry/pricing.py` | `PricingTable`, `load_pricing`, `estimate_cost`, `missing_prices`, `megapixels` |
| `backend/app/telemetry/context.py` | `telemetry_scope`, `request_scope`, `current_*` |
| `backend/app/telemetry/metered.py` | `MeteredFoundryClient`, `TelemetrySink` |
| `backend/app/telemetry/middleware.py` | `RequestIdMiddleware` |
| `backend/app/telemetry/summary.py` | `CostSummary`, `summarize` (totales, por rol, día y despliegue) |
| `backend/app/telemetry/__init__.py` | `create_metered_client` (avisa de despliegues sin precio) |
| `backend/app/telemetry/__main__.py` | CLI `simular` |
| `backend/app/api/v1/costs.py` | `GET /projects/{id}/costs`, `GET /pricing` |
| `backend/app/foundry/{types,azure,mock}.py` | `Usage` con caché, escritura en caché y desglose texto/imagen |
| `backend/app/foundry/smoke.py` | Muestra el coste estimado de cada llamada real |
| `backend/app/storage/repository.py` | `append_telemetry`, `read_telemetry` |
| `shared/src/shared/models.py` | `TelemetryRecord`; `TelemetryLog.records` tipado |
| `backend/app/main.py` | Cliente medido + `RequestIdMiddleware` |
| `backend/Dockerfile`, `docker-compose.yml` | `config/` en la imagen y montado `:ro`; comprobación de imports ampliada |
| `backend/pyproject.toml` | `pyyaml` |
| `postman/interiorai.postman_collection.json` | Carpeta «04 Costes» |
| Tests | `test_telemetry_pricing.py` (11), `test_telemetry_metered.py` (7), `test_api_costs.py` (14) |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 192 passed (5 ejecuciones seguidas) |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Docker: `X-Request-ID` en `/health` | ✅ |
| Docker: `python -m app.telemetry simular <id> --llamadas 6` | ✅ 6 registros, 0 sin precio, 0,04683 € simulados |
| Docker: `GET /costs` con desglose por rol; fichero en `./data/{id}/costes_telemetria.json` | ✅ |
| Docker: `GET /pricing` | ✅ |
| Docker: el script de verificación sigue bloqueado en mock | ✅ |
| Postman CLI | ✅ 21 peticiones, 38 asserts, 0 fallos |

Cubierto por tests: llamada real del auditor del Paso 6 (74/1.084 tokens → 0,0483472 €), caché
y escritura en caché, umbral de 272.000 tokens, Data Zone, texto frente a imagen en GPT-image,
FLUX exacto (1024² → 0,027041 €) y `ceil` con referencias, despliegue sin precio, YAML ausente o
inválido; el envoltorio registra contexto, megapíxeles, errores con uso, no registra roles
inválidos ni llamadas sin proyecto, tolera fallos al guardar; agregados, `limit`, proyecto
inexistente, 30 escrituras concurrentes sin pérdidas; CLI en mock, bloqueo en azure, ids
inválidos.

### Coste estimado de la verificación real del Paso 6

| Llamada | Coste estimado |
|---------|----------------|
| PROMPT_ENGINEER (gpt-6.1-sol) | 0,000649 € |
| CONTEXT_MANAGER (gpt-6-luna) | 0,000035 € |
| GEOMETRIC_AUDITOR (gpt-6-astra, `max`) | 0,048347 € |
| FAST_DRAFT (gpt-image-2.5-flare) | 0,005280 € |
| STRUCTURAL_COMPOSER (gpt-image-2.5-sunburst) | 0,009808–0,012588 €¹ |
| PHOTOREALISTIC_RENDERER (FLUX.2-pro) | 0,027041 € |
| **Total** | **≈ 0,091–0,094 €** |

¹ En el Paso 6 aún no se guardaba el desglose texto/imagen: rango entre «toda la entrada como
texto» y «toda como imagen». El auditor supone algo más de la mitad del total.

Corrección respecto a la propuesta: el ejemplo del auditor se anunció como 0,0484 €; el cálculo
correcto es 0,0483472 €.

## 5. Estado final

✅ Cerrado — rama `feat/paso-07`, PR #6 revisada y mergeada por el usuario.

## 6. Pendiente / futuro

- B-011: contrastar el coste estimado (y el redondeo de MP) con Azure Cost Management.
- B-012: `costes_telemetria.json` se reescribe entero en cada registro; rotación o JSONL si crece mucho (Paso 15).
- Los precios de caché de GPT-image (`cached_input_*`) no se aplican: la API no informa de ese uso.
