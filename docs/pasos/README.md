# Bitácora de pasos

Cada paso tiene su propio documento con: objetivo, decisiones, implementación,
validación, estado final y pendientes. Lo diferido se consolida en
[BACKLOG.md](BACKLOG.md).

| Paso | Documento | Rama | Estado |
|------|-----------|------|--------|
| 0 | [Plan y decisiones](paso-00-plan-y-decisiones.md) | `main` | ✅ Cerrado |
| 1 | [Repo seguro y documentación del agente](paso-01-repo-seguro.md) | `feat/paso-01` | ✅ Cerrado |
| 2 | [Configuración central (Pydantic Settings)](paso-02-configuracion.md) | `feat/paso-02` | ✅ Cerrado |
| 3 | [Esqueleto Docker](paso-03-docker.md) | `feat/paso-03` | ✅ Cerrado |
| 4 | [Modelo de dominio y almacenamiento](paso-04-almacenamiento.md) | `feat/paso-04` | ✅ Cerrado |
| 5 | [API REST de proyectos y assets](paso-05-api.md) | `feat/paso-05` | ✅ Cerrado |
| 6 | [Abstracción Azure AI Foundry](paso-06-foundry.md) | `feat/paso-06` | ✅ Cerrado |
| 7 | [Telemetría y costes](paso-07-telemetria.md) | `feat/paso-07` | ✅ Cerrado |
| 8 | [Pipelines de texto](paso-08-pipelines-texto.md) | `feat/paso-08` | ✅ Cerrado |
| 9 | [Pipelines de imagen](paso-09-pipelines-imagen.md) | `feat/paso-09` | ✅ Cerrado |
| 10 | [Auditor geométrico + HITL](paso-10-auditor-hitl.md) | `feat/paso-10` | ✅ Cerrado |
| 11 | [UI: shell, tema y proyectos](paso-11-ui-proyectos.md) | `feat/paso-11` | ✅ Cerrado |
| 12 | [UI: assets](paso-12-ui-assets.md) | `feat/paso-12` | ✅ Cerrado |
| 13a | [UI: Estudio (ciclo HITL)](paso-13a-ui-estudio.md) | `feat/paso-13a` | ✅ Cerrado |
| 13b | [UI: Estudio (retoques e inpainting)](paso-13b-retoques.md) | `feat/paso-13b` | ✅ Cerrado |
| 14 | [UI: dashboard de costes](paso-14-ui-costes.md) | `feat/paso-14` | ✅ Cerrado |
| 15a | [CI, Dependabot y seguridad del repositorio](paso-15a-ci-seguridad.md) | `feat/paso-15a` | ✅ Cerrado |
| 15b | [Contenedores, papelera y versión 1.0.0](paso-15b-version-1.md) | `feat/paso-15b` | ✅ Cerrado |

Mantenimiento posterior a la 1.0.0:

| Fecha | Documento | Rama | Estado |
|-------|-----------|------|--------|
| 2026-10-23 | Alinear uv 0.13 en la CI (PR #19) | `chore/uv-0.13` | ✅ Cerrado |
| 2026-10-23 | [Contraste con la factura real de octubre](mantenimiento-2026-10-factura.md) | `fix/precios-facturados` | 🧪 En validación |

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
