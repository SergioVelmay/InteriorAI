# Paso 16 — Mejoras del backlog

## 1. Objetivo

Resolver las seis mejoras opcionales que quedaban en el backlog tras la 1.0.0, con un commit
por mejora y las decisiones del usuario antes de implementarlas.

## 2. Decisiones tomadas

| Mejora | Decisión del usuario | Resultado |
|--------|----------------------|-----------|
| **B-022** Fichas en el coste acumulado | Implementar | Hecho |
| **B-012** Telemetría en JSONL | Migración automática conservando el original | Hecho |
| **B-021** Avisos de gasto | Umbrales en `.env`: **3 € por proyecto y 10 € en total**; solo avisan | Hecho |
| **B-017** Auditoría en segundo plano | **No implementar** (privacidad: exige `store=true` con imágenes) | Cerrado |
| **B-020** Renderizador a 1920×1080 directo | Autoriza una llamada real | Comprobado: no sirve |
| **B-008** Actualizar Postman CLI | La actualiza Claude | 1.76.0 |

## 3. Implementación (un commit por mejora)

| Commit | Cambios |
|--------|---------|
| **B-022** | `AssetAnalysis.request_id` (se conserva al validar); `chain_cost` suma las indexaciones de las referencias que usó el brief (fichas anteriores: emparejadas por hora, ±10 s); `RenderChainCost.references`; texto del visor |
| **B-012** | `app/storage/telemetry_log.py`: `costes_telemetria.jsonl`, una línea por llamada; migración del `.json` al arrancar y al usar un proyecto (el original queda como `.json.migrado`); una línea cortada al final se ignora y no se pega a la siguiente. `AGENTS.md`: única excepción a la escritura atómica |
| **B-021** | `COST_ALERT_PROJECT_EUR` / `COST_ALERT_TOTAL_EUR` (`CostAlertSettings`); `GET /api/v1/costs/alerts` (gasto real, sin simulación); distintivos en la cabecera, aviso en Costes y aviso adicional en el Estudio al lanzar una acción con coste; Postman |
| **B-017** | Solo backlog: descartado |
| **B-020** | Docstring de `generation_size`, guía de Azure y backlog |
| **B-008** | Solo backlog (la CLI está en el equipo del usuario) |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 350 passed (fichas en la cadena, JSONL, avisos, configuración) |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Migración JSONL sobre una **copia** de los datos reales | ✅ mismos registros e importes en los dos proyectos; original conservado como `.json.migrado` |
| **B-020**, llamada real al renderizador (≈ 0,04 €) | Pedida 1920×1080 → **devuelta 1920×1072**: acepta el tamaño pero redondea hacia abajo al múltiplo de 16 en silencio. Se mantiene pedir 1920×1088 y recortar |
| **B-008**, Postman CLI | 1.73.0 → **1.76.0**; carpeta «01 Sistema»: 3 peticiones correctas (la única comprobación fallida exige `mock` y el entorno local está en `azure`) |
| CI de la PR | (se completa con el resultado) |

Los contenedores locales estaban parados: se arrancaron solo para la llamada de B-020 y la
prueba de Postman, y se volvieron a parar. Los datos reales se migrarán a JSONL al reconstruir
Docker tras el merge.

## 5. Estado final

🧪 En validación — rama `feat/paso-16`, Pull Request en GitHub.

## 6. Pendiente / futuro

- B-023 (capturas del README) y B-024 (quitar el forzado de Pillow 13 cuando Gradio lo admita).
