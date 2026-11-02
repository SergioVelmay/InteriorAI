# Paso 42 — Botones bloqueados y apagados

## 1. Objetivo

Segundo paso del [plan de la versión 4.1.0](plan-version-4-1.md) (B-110): que ningún botón se
pueda volver a pulsar mientras la aplicación trabaja (la IA genera, se analiza una referencia,
se carga una imagen o hay una confirmación abierta) y que un botón desactivado se vea apagado.

## 2. Análisis (todas las pestañas)

| Pestaña | Botones y zonas pulsables | Antes |
|---------|---------------------------|-------|
| Proyectos | Galería, «Crear proyecto», «Guardar cambios», «Mover a la papelera», «Confirmar» y «Cancelar» de la papelera | Todo pulsable mientras se procesaba |
| Referencias | Galería, subida, «Subir y analizar», «Cancelar», «Guardar notas», «Volver a analizar», «Marcar todo», «Desmarcar todo», «Guardar ficha» | Todo pulsable durante el análisis (30-60 s), también volver a analizar |
| Bocetos, Composición, Render final | Galería, «Seleccionar», los 7 botones con IA, «Confirmar (con coste)» y «Cancelar», el editor de retoque, los iconos del visor | Solo se desactivaba el botón pulsado; con una confirmación abierta, los demás botones con IA y la galería seguían pulsables; al abrir otra imagen, todo pulsable mientras se veía «procesando» |
| Costes IA | «Actualizar», «Descargar CSV», tablas | Pulsable mientras cargaba |

Además, Gradio solo bajaba la opacidad de un botón desactivado: «Seleccionada ●» o «Generar
bocetos» sin referencias se veían casi blancos, como activos.

## 3. Decisiones tomadas (usuario, 2026-11-02)

| Tema | Decisión |
|------|----------|
| Alcance | Todos los botones de todas las pestañas, también mientras se carga una imagen en el visor |
| Qué sigue libre | Las pestañas y los desplegables, para consultar otras cosas mientras la IA trabaja |
| Aspecto | Un botón bloqueado o desactivado, gris («apagado»), no blanco ni rojo |

## 4. Implementación

| Parte | Cambios |
|-------|---------|
| Bloqueo (`ui/locks.py`, `BUSY_LOCK_JS`) | Una regla común, en el navegador: mientras haya un «procesando» visible (`.progress-text`) en la pestaña a la vista, o una confirmación `#iai-confirm-*` abierta, marca sus botones (también las miniaturas, que en Gradio son botones) con `data-iai-locked`. Libres: pestañas, cabeceras de los desplegables, avisos y, con la confirmación, sus dos botones. Los clics y las teclas Intro y Espacio del usuario sobre un botón marcado se anulan en captura; los clics que hace el propio JS (puentes ocultos) pasan (`isTrusted`). Un `MutationObserver` lo recalcula en cada cambio de la página, una vez por fotograma |
| Carga (`app.py`) | `APP_JS`: el JS de siempre (tema, tooltips, textos) y el del bloqueo |
| Aspecto (`theme.CSS`) | `:disabled` y `[data-iai-locked]`: fondo gris oscuro, texto atenuado, sin efecto al pasar el ratón y cursor de prohibido; miniaturas e iconos bloqueados, atenuados |
| Pruebas E2E (`e2e/conftest.py`) | Cada clic espera a que el botón se desbloquee, como haría una persona (las pruebas pulsaban, por ejemplo, justo tras recargar la página, y ahora el clic se ignora) |
| Documentación | Manual (aviso en la portada), referencia de la interfaz y `docs/agent/gradio_ui.md` |

Sirve igual para los botones nuevos de los descartes (Paso 43).

## 5. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ Test nuevo: el JS de la página incluye el bloqueo con sus excepciones y el CSS apaga desactivados y bloqueados |
| Navegador (aplicación local en simulación tras un proxy que anuncia Azure, red lenta emulada; nunca se pulsa «Confirmar») | ✅ «Seleccionada ●» se ve gris (`rgb(39, 39, 42)`, texto `rgb(113, 113, 122)`); en reposo, nada bloqueado. Al abrir otra imagen: 20 botones y miniaturas bloqueados, las pestañas libres (se cambia de pestaña durante el proceso); un clic en otra miniatura mientras tanto se ignora (queda la pedida). Con la confirmación de 8 bocetos en calidad alta (≈ 0,50 €): libres solo las pestañas, «Confirmar», «Cancelar» y el aviso; al cancelar, todo vuelve. Referencias y Costes IA, bloqueados mientras cargan y libres al terminar |
| Playwright de extremo a extremo (aplicación local en simulación) | ✅ 6 passed (con el clic que espera al desbloqueo; sin él, fallaban 4 por pulsar mientras cargaba) |
| `mkdocs build --strict` | ✅ |
| pre-commit | ✅ |
| CI de la PR #60 | ✅ lint y tests, gitleaks, Docker con newman y Playwright (en Chromium, con el bloqueo), y la construcción de la documentación |

Coste real del paso: 0 €.

## 6. Estado final

✅ Cerrado — rama `feat/paso-42`, PR #60 revisada y mergeada por el usuario (2026-11-02). Docker
reconstruido.

## 7. Pendiente / futuro

- Paso 43: descartes de candidatos (B-109).
