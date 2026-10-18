# Paso 10 — Auditor geométrico y cierre del ciclo HITL

## 1. Objetivo

Que el **GEOMETRIC_AUDITOR** compare una composición o un render final con la captura de
SketchUp y entregue un informe de desviaciones antes de que el usuario decida, y cerrar el
ciclo Human-in-the-Loop con el **rechazo con comentarios**, que regenera la imagen.

Ciclo de vida de un render: **generado → (auditado) → seleccionado | descartado | rechazado →
nueva imagen** (`previous_attempt_id`).

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| **Auditoría a demanda** (aprobado por el usuario) | Es el rol más caro; útil sobre todo en un proceso automático sin HITL. | Auditar cada imagen automáticamente. |
| **Auditoría opcional para seleccionar** (aprobado) | El usuario decide; el informe es apoyo, no una puerta. | Exigirla para composiciones y finales. |
| **Prueba real: solo el render final** (aprobado) | Limitar coste. | Auditar también la composición. |
| La referencia de la auditoría es **la captura de origen**, siguiendo la cadena de renders | El render final deriva de la composición, pero la verdad geométrica es SketchUp. | Comparar con la composición. |
| `AuditReport` estricto: veredicto, puntuación, checks por 6 aspectos, desviaciones con severidad, correcciones **en inglés** y resumen | Accionable: las correcciones se reutilizan en la siguiente iteración. | Texto libre. |
| Historial de auditorías por render, con coste, esfuerzo, despliegue y versión del prompt | Trazabilidad. | Solo la última. |
| Imágenes de auditoría a ≤ 1.536 px; tope de 12.000 tokens de salida | Cotas legibles; coste acotado. | — |
| Rechazo con `feedback`; `regenerate` (por defecto) repite la etapa con las mismas entradas y añade al prompt los comentarios y, si se pide, las correcciones de la última auditoría | Iteración guiada sin rehacer la cadena. `rechazado` es terminal. | — |
| **Incidente → corrección (decisión del usuario): nunca reintentar un timeout** | La primera auditoría (`max`, timeout 120 s) agotó el tiempo y el SDK la reintentó 3 veces (484 s): cada intento pudo facturarse. Ahora el SDK no reintenta; los reintentos propios solo ante 429/503 (Azure no procesó). También en el renderizador. | Reintentos del SDK. |
| **`GEOMETRIC_AUDITOR_TIMEOUT_S=900`** (usuario) en `.env.example` y `.env` | Las auditorías con razonamiento tardan minutos. | Timeout global. |
| **`GEOMETRIC_AUDITOR_REASONING_EFFORT=medium`** (usuario) | La auditoría es opcional; `max` dispara latencia y coste. | `max`. |
| **Render final en PNG** (usuario) en lugar de JPEG | Sin artefactos de compresión; el renderizador cobra por MP, no por formato. Formato de cada etapa en una única tabla (`_STAGE_ROLES`). | JPEG. |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `shared/src/shared/models.py` | `AuditCheck`, `AuditDeviation`, `AuditReport`, `RenderAudit`; `RenderStatus.REJECTED`; `RenderRecord.audits/feedback/previous_attempt_id` |
| `backend/app/pipelines/auditor.py` | `audit_render`, `reference_asset_id` |
| `backend/app/pipelines/prompts/geometric_auditor.md` | Prompt de sistema del auditor |
| `backend/app/pipelines/renders.py` | `reject_render`, `feedback_prompt`, `_STAGE_ROLES` (rol y formato; todo PNG), transiciones con `rechazado` |
| `backend/app/api/v1/renders.py` | `POST /renders/{id}/audit`, `POST /renders/{id}/reject` |
| `backend/app/foundry/azure.py` | `_openai_call`: SDK sin reintentos; reintentos propios solo 429/503; timeout del auditor; el renderizador no reintenta timeouts |
| `shared/src/shared/settings.py`, `.env.example`, `.env` | `GEOMETRIC_AUDITOR_TIMEOUT_S`, esfuerzo `medium` por defecto |
| `backend/Dockerfile` | La comprobación del build carga el prompt del auditor |
| `postman/interiorai.postman_collection.json` | Auditoría y rechazo en la carpeta «solo mock» |
| Tests | `test_api_audit.py` (8), `test_foundry_azure.py` (+6), `test_settings.py` (+1) |

## 4. Validación

### Tests, Docker y Postman (mock)

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 250 passed (3 ejecuciones) |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Auditoría en Docker (mock) sobre un proyecto desechable | ✅ |
| Postman CLI (mock) | ✅ 39 peticiones, 68 asserts, 0 fallos |

Cubierto por tests: auditoría frente a la captura de origen (no la composición), 2 imágenes
≤ 1.536 px, esquema, tope de tokens, contexto del brief, coste y esfuerzo registrados;
historial; bocetos no auditables (422); render inexistente (404); seleccionar sin auditar;
auditoría incompleta → 502 con coste registrado; rechazo con comentarios y correcciones del
auditor, sin correcciones, sin regenerar; `rechazado` terminal; **un timeout se intenta una sola
vez** (texto y renderizador) aunque `MAX_RETRIES=3`; 429 y 503 sí se reintentan, 500 no;
timeout propio del auditor (900 s frente a 120 s); valores por defecto `medium`/900 s.

### Pruebas reales contra Azure (proyecto real del usuario)

| # | Llamada | Resultado | Coste |
|---|---------|-----------|-------|
| 1 | Auditoría del render final con `max` (timeout 120 s) | ❌ **504 tras 484 s** (4 intentos por reintentos del SDK) | ⚠️ desconocido (B-016) |
| 2 | Auditoría del render final con **`medium`** (900 s, sin reintentos) | ✅ 43 s; 5.895 entrada (casi todo `cache_write`) / 1.875 salida / 506 razonamiento | 0,147338 € |
| 3 | Rechazo de la composición v1 con comentarios + regeneración (sunburst `medium`) | ✅ composición v2 con las 4 correcciones | 0,031871 € |
| 4 | Render final v2 en **PNG** (FLUX) con las correcciones del auditor como indicaciones | ✅ 1920×1280, 3,63 MB | 0,092274 € |
| | **Total registrado** | | **0,271483 €** + lo facturado del intento 1 |

Informe de la auditoría (`no_conforme`, 73/100): conserva la disposición, la chaiselongue a la
derecha, los tres reposacabezas y la textura; **desviación alta**: el paso hacia el distribuidor a
la derecha de la columna de cocina sustituido por una pared; medias: encuadre (cámara menos
cenital y 3:2 frente a 16:9), silueta abultada de la chaiselongue, placa de gas en lugar de placa
plana; bajas: tono de las paredes, luz y reflejos. No certifica las medidas desde otra perspectiva
(no las inventa).

Resultado de la corrección: composición v2 y render final v2 con el paso recuperado, placa plana,
silueta rectilínea, paredes en rojo anaranjado y un verde más oscuro y oliva (más cercano a la
inspiración). Decisiones del usuario: composición v2 «la buena», render final v2 **definitivo**;
render final v1 rechazado sin regenerar («Sustituido por la v2 tras la auditoría geométrica»).

## 5. Estado final

✅ Cerrado — rama `feat/paso-10`, PR #9 revisada y mergeada por el usuario.

## 6. Pendiente / futuro

- B-016: revisar en Azure Cost Management lo facturado por los 4 intentos de la auditoría fallida.
- B-017: *background mode* de la Responses API para llamadas de minutos (exige `store=true`).
- B-018: render final con la misma proporción que la captura (16:9 → 1920×1088 en el renderizador).
