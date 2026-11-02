# Paso 43 — Descartes de candidatas

## 1. Objetivo

Tercer paso del [plan de la versión 4.1.0](plan-version-4-1.md) (B-109): apartar de las
galerías de Bocetos, Composición y Render final las candidatas que estorban, sin borrarlas, y
poder recuperarlas.

## 2. Decisiones tomadas (usuario, 2026-11-02)

| Tema | Decisión |
|------|----------|
| Cómo se descarta | Un aspa en cada miniatura salvo la seleccionada, y «Descartar» junto a «Seleccionar» en la imagen en grande; en la seleccionada solo queda «Seleccionada ●», apagado |
| Dónde van | Un desplegable «Descartados (n)» al final de cada pestaña, con el mismo estilo de galería, cerrado por defecto y **solo si hay alguna** |
| Recuperar | Un ✓ sobre cada descartada la devuelve a las candidatas; las descartadas no se abren en grande (antes se recuperan) |
| Borrado | Ninguno: es un estado, recuperable |
| La IA | No ve las descartadas entre las generaciones anteriores de la etapa |
| Manual | Capturas actualizadas (copia local en simulación, sin coste) |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Modelo (`shared/models.py`) | `RenderStatus.DISCARDED = "descartado"` |
| Transiciones (`pipelines/renders.py`) | `generado ↔ descartado` además de las de selección; `set_discarded` (la seleccionada no se descarta: 409; recuperar solo una descartada). Una descartada no se selecciona sin recuperarla (409) |
| Uso (`hitl.ensure_usable`) | Una descartada no se usa: ni «Otra versión», ni retoque, ni auditoría (409, «recupérala antes de usarla») |
| Prompts (`prompt_writer.previous_section`) | Las descartadas, fuera de las generaciones anteriores de la etapa |
| API | `POST …/renders/{id}/discard` y `POST …/renders/{id}/restore` (`RenderRecord`); esquema OpenAPI regenerado |
| Interfaz | Candidatas sin las descartadas (`renders_of`) y descartadas aparte (`discarded_of`, mismo orden); «Descartar» en el visor; `_discarded`: desplegable al final de cada pestaña y botón oculto del puente; `ui/thumb_actions.py` (nuevo): aspa y ✓ sobre las miniaturas, que dejan «discard:índice» o «restore:índice» y pulsan el puente; la descartada no se abre al pulsarla. Respeta el bloqueo del Paso 42 |
| Portada y resumen | La portada no es nunca una descartada; el resumen del proyecto cuenta las descartadas aparte |
| Postman | Descartar la seleccionada (409), descartar otro render final, seleccionarlo descartado (409) y recuperarlo |
| Manual | Bocetos: «Descartar y recuperar», con tres capturas; Composición y Render final remiten a ella; galerías de Composición y Render final con el aspa y el atardecer descartado. En la copia local, el render de noche vuelve a estar seleccionado y sin las tres pruebas posteriores del usuario (con personas y un perro, fuera del caso) |
| Documentación | Referencia (datos, API e interfaz), `docs/agent/fast_api_specs.md` y `docs/agent/gradio_ui.md` |

## 4. Además: cambio de proyecto mientras se procesa (B-111)

Observación del usuario durante la revisión: subiendo una referencia (hasta un minuto) cambió
de proyecto, porque las pestañas siguen libres y el bloqueo del Paso 42 solo actúa en la
pestaña a la vista. Al terminar, la respuesta de la subida pintó en Referencias la referencia
del proyecto anterior; al guardar su ficha, la aplicación la buscó en el proyecto activo
(«Asset no encontrado») y el cambio se perdió.

| Parte | Cambios |
|-------|---------|
| Bloqueo (`ui/locks.py`, `PROJECT_SWITCH`) | Elegir otro proyecto, crear uno o moverlo a la papelera se bloquea mientras haya algo procesándose **en cualquier pestaña**, también en las que no están a la vista (Gradio solo deja los «procesando» en la página mientras el evento sigue en marcha) |
| Defensa en Referencias | El panel recuerda de qué proyecto es lo que muestra (`shown_project`): «Guardar ficha», «Guardar notas» y «Volver a analizar» con el panel de otro proyecto no guardan nada en el activo; avisan y recargan la pestaña con el proyecto activo |
| Identificadores | `#iai-delete` y `#iai-confirm-delete` en Proyectos |

### Y el botón rojo al pasar el ratón (B-112)

Otra observación del usuario: el botón rojo («Confirmar (con coste)», «Confirmar: mover a la
papelera») no cambiaba al pasar el ratón, a diferencia de los blancos y los grises. Ahora pasa
de `#7f1d1d` a un rojo más vivo, `#b91c1c` (`theme.CSS`), solo si está activo: apagado o
bloqueado sigue gris (Paso 42). Comprobado en el navegador (confirmación de 8 bocetos en calidad
alta, cancelada): `rgb(127, 29, 29)` → `rgb(185, 28, 28)`.

## 5. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ Tests nuevos: descartar y recuperar con sus 409; una descartada no se usa (otra versión, retoque, auditoría) ni entra en el contexto del `PROMPT_ARCHITECT`; candidatas y descartadas; visor y desplegable; portada |
| Navegador (aplicación local en simulación, copia de los datos) | ✅ Aspa en las 7 candidatas y no en la seleccionada; al descartar, «Descartados (1)» aparece cerrado; un clic en la descartada no la abre; el ✓ la devuelve y el desplegable desaparece; «Descartar» desde el visor muestra la seleccionada; igual en Composición y Render final |
| Playwright de extremo a extremo (aplicación local en simulación) | ✅ 7 passed (nuevo `test_e2e_discards.py`) |
| Postman CLI (backend local en simulación) | ✅ 53 peticiones, 95 comprobaciones |
| B-111 en el navegador (simulación, red lenta) | ✅ Con la subida en marcha en Referencias, en Proyectos la galería aparece apagada y el clic en otro proyecto se ignora; al terminar, el cambio funciona y Referencias muestra las del proyecto nuevo. Test nuevo: con el panel de otro proyecto, guardar ficha, notas o volver a analizar no escriben nada y recargan. E2E: 7 passed |
| `mkdocs build --strict` | ✅ |
| pre-commit | ✅ |
| CI de la PR #61 | ✅ lint y tests, gitleaks, Docker con newman (colección con los descartes) y Playwright (7 pruebas, también la de los descartes), y la construcción de la documentación |
| CI de la PR #61 con B-111 | ✅ lint y tests, gitleaks, Docker con newman y Playwright, y la construcción de la documentación |
| CI de la PR #61 con B-112 | ✅ lint y tests, gitleaks, Docker con newman y Playwright, y la construcción de la documentación |

Coste real del paso: 0 €.

## 6. Estado final

✅ Cerrado — rama `feat/paso-43`, PR #61 revisada y mergeada por el usuario (2026-11-02).

## 7. Pendiente / futuro

- Paso 44: versión 4.1.0.
