# Paso 55 — La superposición del esquema 3D (B-123, B-124, B-125)

## 1. Objetivo

Hacer legible la medida de la superposición en Bocetos, Composición y Render Final, aclarar los
textos de sus dos casillas y eliminar el salto de scroll causado por apilar tres visores. No se
modifica la fidelidad del pie de miniatura (`geometry_caption`), la exclusión entre casillas ni la
opacidad.

## 2. Decisiones tomadas

| Tema | Decisión |
|------|----------|
| Medida | Un `geometry_md` independiente, debajo del título: sin casillas o con «original» muestra `fidelity()`; con «corregido» muestra `alignment()`; al desmarcar vuelve a la medida original. Sin esquema, proyecto o imagen activa, queda vacío. |
| Visor | Un solo `viewer`; `overlay_handler()` cambia su valor entre la imagen normal y la superpuesta. No se añade JavaScript de scroll. |
| Datos y coste | Mantener `AI_PROVIDER_MODE=mock`. Ejecutar Docker/E2E en un proyecto aislado con volumen temporal y puertos distintos, para no montar ni cambiar `./data` ni reiniciar los servicios actuales. No usar imágenes reales del usuario ni generar imágenes con IA. |
| Capturas | No rehacer ni manipular las tres capturas existentes; quedan pendientes para el usuario (B-126). |
| Backlog | B-123–B-125 siguen abiertos durante la revisión; se marcan resueltos solo después de integrar la PR, conforme al flujo del proyecto. |

## 3. Implementación

| Archivo | Cambio |
|---------|--------|
| `frontend/ui/tabs/studio.py` | Un visor y un bloque de medida por etapa; nuevos textos de casillas; medida original por defecto y medida ajustada al marcar «corregido». |
| `frontend/ui/theme.py` | Retira el CSS `.iai-geometry`, que deja de tener uso. |
| `frontend/tests/test_ui_studio.py` | Comprueba labels, ausencia de componentes antiguos, exclusión, medidas y recuperación del visor/medida original. |
| `e2e/test_e2e_studio.py` | Comprueba el estado de las medidas, el único visor y la estabilidad de scroll/altura en el navegador con una referencia sintética. |
| `docs/manual/bocetos.md`, `docs/manual/composicion.md`, `docs/manual/render-final.md` | Actualiza los textos; identifica las capturas antiguas como pendientes sin modificarlas. |
| `docs/agent/gradio_ui.md` | Actualiza el mapa técnico del bloque de superposición. |
| `docs/pasos/BACKLOG.md`, `docs/pasos/README.md`, `docs/pasos/paso-55-superposicion.md` | Registra B-123–B-126, el índice y este documento. |

## 4. Validación

Se anotan solo resultados observados. La CI se completará tras abrir la PR; la comprobación
manual pendiente conserva el motivo indicado en la tabla.

| Comprobación | Resultado |
|--------------|-----------|
| `uv run ruff check . --fix && uv run ruff format .` | ✅ `ruff check`: All checks passed; `ruff format`: 226 archivos sin cambios. En PowerShell se ejecutaron en secuencia comprobando el código de salida. |
| `uv run pytest frontend/tests/test_ui_studio.py -k overlay -q` | ✅ 2 passed, 28 deselected en 11,06 s. |
| `uv run pytest` | ✅ 388 passed en 103,21 s. |
| `uvx pre-commit run --all-files` | ✅ Todos los hooks aplicables pasaron; los bloqueos de `.env` y `data/` se omitieron porque no había archivos coincidentes. |
| Docker aislado, en modo `mock`, con volumen temporal | ✅ `docker compose up --build -d` con override temporal y proyecto `interiorai-paso55`: `data-init` terminó, backend y frontend quedaron healthy; `/health` devolvió `status=ok`, `mode=mock`, versión `4.1.0`; frontend respondió HTTP 200. `./data` y el stack existente no se montaron ni reiniciaron. |
| `uv run --group e2e pytest e2e --browser-channel msedge` | ✅ 9 passed en 158,88 s; 1 aviso `PytestRemovedIn10Warning` por fixture legacy en `test_e2e_costs.py::test_costs_tab`. |
| Comprobación manual del scroll en el navegador | Pendiente: el navegador de control bloqueó la navegación a `localhost` por política; no se eludió. El E2E en Edge sí midió scroll y altura del visor al marcar/desmarcar las dos casillas y pasó. |
| `uv run --group docs mkdocs build --strict` | ✅ Construcción correcta; mostró el aviso de que Material for MkDocs llega al fin de vida el 5 de mayo de 2027 (B-103). |
| CI de la PR | Pendiente |

## 5. Estado final

⏳ En curso — rama `feat/paso-55`; PR y commit pendientes. B-123, B-124 y B-125 quedan abiertos
hasta que el usuario integre el cambio.

## 6. Pendiente / futuro

- B-126: el usuario actualizará `docs/manual/img/bocetos-superposicion.jpg`,
  `composicion-superposicion.jpg` y `render-superposicion.jpg` usando la aplicación y proyectos
  reales. No se modificaron ni regeneraron estas imágenes.
- Después del merge, verificar la integración y marcar B-123, B-124 y B-125 como resueltos en este
  documento, el índice y el backlog.
