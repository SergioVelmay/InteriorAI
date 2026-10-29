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
| 16 | [Mejoras del backlog](paso-16-mejoras.md) | `feat/paso-16` | ✅ Cerrado |
| 17 | [Modelo de datos v2 y migración](paso-17-modelo-datos-v2.md) | `feat/paso-17` | ✅ Cerrado |
| 18 | [Configuración de los modelos de IA](paso-18-config-modelos.md) | `feat/paso-18` | ✅ Cerrado |
| 19 | [Proyectos y cabecera](paso-19-proyectos-cabecera.md) | `feat/paso-19` | ✅ Cerrado |
| 20 | [Costes IA](paso-20-costes-ia.md) | `feat/paso-20` | ✅ Cerrado |
| 21 | [Referencias v2](paso-21-referencias-v2.md) | `feat/paso-21` | ✅ Cerrado |
| 22 | [Estudio I: base común y Bocetos](paso-22-estudio-bocetos.md) | `feat/paso-22` | ✅ Cerrado |
| 23 | [Estudio II: Composición](paso-23-composicion.md) | `feat/paso-23` | ✅ Cerrado |
| 24 | [Estudio III: Render Final](paso-24-render-final.md) | `feat/paso-24` | ✅ Cerrado |
| 25 | [Versión 2.0.0](paso-25-version-2.md) | `feat/paso-25` | ✅ Cerrado |
| 26 | [Roles y Costes IA](paso-26-roles-costes.md) | `feat/paso-26` | ✅ Cerrado |
| 27 | [Estilo común, Proyectos y Referencias](paso-27-estilo-proyectos-referencias.md) | `feat/paso-27` | ✅ Cerrado |
| 28 | [Bocetos](paso-28-bocetos.md) | `feat/paso-28` | ✅ Cerrado |
| 29 | [Composición y Render Final](paso-29-composicion-render.md) | `feat/paso-29` | ✅ Cerrado |
| 30 | [Detalles finales](paso-30-detalles-finales.md) | `feat/paso-30` | ✅ Cerrado |
| 31 | [Capturas y versión 3.0.0](paso-31-version-3.md) | `feat/paso-31` | ✅ Cerrado |

Versión 2.0.0 (publicada el 2026-10-25): [plan de acción](plan-version-2.md), Pasos 17 a 25,
entradas B-023 a B-055
del [backlog](BACKLOG.md).

Versión 3.0.0 (publicada el 2026-10-27): [plan de acción](plan-version-3.md), Pasos 26 a 31, entradas
B-057 a B-093 (observaciones O-1 a O-37 del usuario) y B-023 del [backlog](BACKLOG.md).

Mantenimiento posterior a la 1.0.0:

| Fecha | Documento | Rama | Estado |
|-------|-----------|------|--------|
| 2026-10-23 | Alinear uv 0.13 en la CI (PR #19) | `chore/uv-0.13` | ✅ Cerrado |
| 2026-10-23 | [Contraste con la factura real de octubre](mantenimiento-2026-10-factura.md) | `fix/precios-facturados` | ✅ Cerrado |
| 2026-10-23 | Dependencias con alertas de seguridad: Pillow 13 forzado, certifi y brotli (PR #22; B-024) | `fix/seguridad-dependencias` | ✅ Cerrado |

Después de la 3.0.0:

| Paso | Documento | Rama | Estado |
|------|-----------|------|--------|
| 32 | [Prompts del PROMPT_ARCHITECT más precisos](paso-32-prompts.md) (B-054, B-094 a B-097) | `feat/paso-32` | ✅ Cerrado |
| 33 | [Retirar la compatibilidad con la v1](paso-33-sin-v1.md) (B-056) | `feat/paso-33` | ✅ Cerrado |
| 34 | [Web de documentación](paso-34-web.md) (B-099) | `feat/paso-34` | ✅ Cerrado |
| 35 | [Referencia técnica](paso-35-referencia.md) (B-100) | `feat/paso-35` | ✅ Cerrado |
| 36 | [Manual de usuario](paso-36-manual.md) (B-101) | `feat/paso-36` | ✅ Cerrado |
| 37 | [Comunidad del repositorio](paso-37-comunidad.md) (B-102) | `feat/paso-37` | ✅ Cerrado |
| 38 | [Arreglos de la interfaz](paso-38-arreglos.md) (B-104 a B-106) | `feat/paso-38` | ✅ Cerrado |
| 39 | [Precios y costes con la factura real](paso-39-precios.md) (B-098) | `feat/paso-39` | ✅ Cerrado |
| 40 | [Versión 4.0.0](paso-40-version-4.md) | `feat/paso-40` | ✅ Cerrado |

Versión 4.0.0 (publicada el 2026-10-29): [plan de acción](plan-version-4.md), Pasos 32 a 40, entradas B-054,
B-056, B-094 a B-102, B-104 a B-106 del [backlog](BACKLOG.md).

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
