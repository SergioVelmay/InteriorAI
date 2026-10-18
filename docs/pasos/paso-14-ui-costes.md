# Paso 14 — Interfaz: pestaña Costes

## 1. Objetivo

Ver en la interfaz cuánto cuesta la IA: indicadores, desglose por rol, día y proyecto, el
detalle de cada llamada y los precios vigentes, a partir de la telemetría del Paso 7. Además,
el coste acumulado para llegar a cada imagen, en el visor del Estudio.

## 2. Decisiones tomadas

| Decisión | Motivo | Alternativa descartada |
|----------|--------|------------------------|
| **Alcance: proyecto activo o todos** (aprobado), con endpoint global `GET /costs` y desglose por proyecto | Ver el gasto total del estudio, no solo el de un proyecto | Solo el proyecto activo |
| **Simulación excluida por defecto en la interfaz** (aprobado), casilla «Incluir simulación»; la API la incluye por defecto (`include_simulated=true`) por compatibilidad | Las llamadas `mock` no cuestan y distorsionan las cifras | Mezclarlas |
| **Coste acumulado de la cadena** en el visor del Estudio (aprobado), `GET /renders/{id}/cost` | Saber cuánto ha costado llegar a una imagen | Dejarlo para el backlog |
| La cadena se suma por `request_id`: lotes completos, intentos rechazados que la imagen sustituye, retoques y su salida en bruto, auditorías y el brief con sus versiones previas; **sin ramas descartadas** | Lo que de verdad llevó a la imagen, con el coste exacto de cada llamada | Repartir costes por imagen |
| `DesignBrief.request_id` nuevo; los briefs anteriores se emparejan por hora (±10 s) con su llamada de `PROMPT_ENGINEER` | Tu brief v1 coincide al segundo (07:43:24) | Dejar el brief fuera |
| **Alerta de gasto al backlog** (B-021, aprobado) | El gasto es de céntimos | — |
| Gráficos nativos de Gradio (`gr.BarPlot`), colores fijos por rol y eje Y desde 0 | Sin dependencias nuevas (pandas ya venía con Gradio; ahora explícito); con una sola barra el eje automático no la dibujaba | Plotly |
| CSV separado por `;` con BOM UTF-8 | Se abre bien en una hoja de cálculo en español | Coma |
| Las llamadas con error figuran a 0 € con aviso | Un timeout pudo facturarse (B-016) | — |

## 3. Implementación

| Archivo | Descripción |
|---------|-------------|
| `backend/app/telemetry/summary.py` | `CostRecord` (con proyecto), filtro de simulación, `simulated_excluded`, `by_project` |
| `backend/app/telemetry/chain.py` | `render_chain`, `chain_cost` (`RenderChainCost`) |
| `backend/app/api/v1/costs.py` | `include_simulated`, `GET /costs`, `GET /projects/{id}/renders/{id}/cost` |
| `shared/.../models.py`, `pipelines/prompt_engineer.py` | `DesignBrief.request_id` |
| `frontend/ui/cost_views.py` | Indicadores, notas, tablas de los gráficos, registro, CSV, precios, línea de la cadena |
| `frontend/ui/tabs/costs.py` | `build_costs_tab`; `app.py` la recarga al entrar con el alcance elegido |
| `frontend/ui/tabs/studio.py` | Coste acumulado de la cadena en el visor |
| `frontend/ui/theme.py` | Tarjetas de indicadores |
| `postman/` | Costes sin simulación, de todos los proyectos y de la cadena del render final |
| Tests | `test_api_costs.py` (filtro, global, emparejado de briefs anteriores), `test_api_renders.py` (cadena), `test_ui_costs.py` (nuevo) |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 333 passed |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Postman CLI (mock) | ✅ 47 peticiones, 83 comprobaciones |
| Playwright + Edge en Docker, proyecto real (solo lectura) | ✅ 5/5: indicadores (0,6247 €, 12 llamadas, 1 error), filtro por rol, CSV (4 filas), todos los proyectos con desglose, coste de la cadena en el Estudio (0,2969 €) |
| Regresión del Estudio (Playwright) | ✅ 9/9 |

Coste de la cadena del render final del proyecto real (`d48a5331`): **0,2969 €** en 6
llamadas (brief, boceto, dos composiciones, render final y el retoque cuya salida en bruto se
usó). El total del proyecto (0,6247 €) incluye además las ramas descartadas.

Sin llamadas reales a la IA: coste 0 €. Proyectos de prueba eliminados. El proyecto real se
llama ahora «Salón con Sofá Jattebo de Ikea» (renombrado por el usuario).

## 5. Estado final

✅ Cerrado — rama `feat/paso-14`, PR #14 revisada y mergeada por el usuario.

## 6. Pendiente / futuro

- B-021: alerta de gasto por proyecto.
- B-022: incluir la indexación de referencias en el coste de la cadena.
