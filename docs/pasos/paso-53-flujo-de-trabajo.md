# Paso 53 — Documentar el modo de proceder del proyecto

## 1. Objetivo

Documentar el ciclo completo que sigue un agente al trabajar en InteriorAI. El procedimiento debe
ser utilizable leyendo el repositorio, sin depender del historial de conversaciones, y cubrir
desde la petición del usuario hasta la revisión y el cierre después del merge.

Entrada de backlog: [B-122](BACKLOG.md#L128), petición del usuario en este chat (2026-11-07).

## 2. Decisiones tomadas

| Tema | Decisión |
|------|----------|
| Ubicación | `docs/agent/flujo_de_trabajo.md`, fuera de la web pública junto al resto de contexto para agentes |
| Índice de agentes | Enlazar desde «Flujo de trabajo» y «Documentación por materia» de `AGENTS.md` |
| Estructura | Mantener las seis secciones principales de la plantilla de pasos y usar subsecciones cuando ayuden |
| Aprobaciones | Separar autorización del plan, autorización de llamadas reales a IA y revisión/merge de la PR |
| Evidencia | Registrar resultados de comandos y CI solo después de verificarlos; señalar discrepancias entre rama local y GitHub |
| Capturas | Distinguir las capturas del manual (proyectos y renders reales existentes, sin generar) de los fixtures sintéticos E2E |

## 3. Implementación

| Archivo | Cambio |
|---------|--------|
| `docs/agent/flujo_de_trabajo.md` | Añade el ciclo de trabajo, la política de autorización, backlog, pruebas, documentación, Git, PR, CI, cierre y una lista compacta de verificación |
| `AGENTS.md` | Sustituye el resumen escueto por un enlace al procedimiento y lo añade a la lista de documentos bajo demanda |
| `docs/pasos/BACKLOG.md` | Registra B-122 con el origen de la petición en esta conversación y su destino en el Paso 53 |
| `docs/pasos/README.md` | Añade la fila del Paso 53 |

El documento mantiene el contexto para agentes fuera del sitio público: `mkdocs.yml` excluye
`docs/agent/` y `docs/pasos/`.

## 4. Validación

| Comprobación | Resultado |
|--------------|-----------|
| `uv run pytest` | ✅ 387 passed en 90,30 s |
| `uv run ruff check .` | ✅ All checks passed |
| `uv run ruff format --check .` | ✅ 224 files already formatted |
| `uv run --group docs mkdocs build --strict` | ✅ Construcción correcta; mostró el aviso de fin de vida de Material for MkDocs (B-103) |
| `uvx pre-commit run --all-files` | ✅ Hooks aplicables pasaron; los de `.env` y `data/` se omitieron al no haber archivos coincidentes |
| `git diff --check` | ✅ Sin errores de whitespace |
| Playwright E2E | No aplica: no se modificó la interfaz |
| CI de la PR | Pendiente de abrir la PR |

## 5. Estado final

⏳ En curso — rama `feat/paso-53`; falta validar, crear el commit y abrir la PR para revisión del
usuario. El agente no hará merge.

## 6. Pendiente / futuro

- Tras abrir la PR, registrar aquí los resultados reales de `CI de la PR #N`.
- Tras el merge del usuario, reconstruir Docker, comprobar el healthcheck y cerrar este paso en
  esta bitácora y en el índice.
- B-122 queda abierto hasta que el Paso 53 esté mergeado.
