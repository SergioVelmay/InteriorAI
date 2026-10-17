# Bitácora de pasos

Cada paso tiene su propio documento con: objetivo, decisiones, implementación,
validación, estado final y pendientes. Lo diferido se consolida en
[BACKLOG.md](BACKLOG.md).

| Paso | Documento | Rama | Estado |
|------|-----------|------|--------|
| 0 | [Plan y decisiones](paso-00-plan-y-decisiones.md) | `main` | ✅ Cerrado |
| 1 | [Repo seguro y documentación del agente](paso-01-repo-seguro.md) | `feat/paso-01` | ✅ Cerrado |
| 2 | [Configuración central (Pydantic Settings)](paso-02-configuracion.md) | `feat/paso-02` | ✅ Cerrado |
| 3 | Esqueleto Docker | — | ⏳ Pendiente |
| 4 | Modelo de dominio y almacenamiento | — | ⏳ Pendiente |
| 5 | API REST de proyectos y assets | — | ⏳ Pendiente |
| 6 | Abstracción Azure AI Foundry | — | ⏳ Pendiente |
| 7 | Telemetría y costes | — | ⏳ Pendiente |
| 8 | Pipelines de texto | — | ⏳ Pendiente |
| 9 | Pipelines de imagen | — | ⏳ Pendiente |
| 10 | Auditor geométrico + HITL | — | ⏳ Pendiente |
| 11 | UI: shell, tema y proyectos | — | ⏳ Pendiente |
| 12 | UI: assets | — | ⏳ Pendiente |
| 13 | UI: Estudio (HITL) | — | ⏳ Pendiente |
| 14 | UI: dashboard de costes | — | ⏳ Pendiente |
| 15 | Hardening, CI y release | — | ⏳ Pendiente |

## Plantilla de documento de paso

```markdown
# Paso NN — Título

## 1. Objetivo
## 2. Decisiones tomadas        (qué, alternativas descartadas, por qué)
## 3. Implementación            (archivos creados/modificados)
## 4. Validación                (comandos ejecutados + resultado real)
## 5. Estado final              (✅ Cerrado / ⚠️ Cerrado con pendientes — rama, commit)
## 6. Pendiente / futuro        (se replica en BACKLOG.md)
```
