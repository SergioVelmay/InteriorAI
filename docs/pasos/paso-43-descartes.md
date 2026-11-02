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

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ Tests nuevos: descartar y recuperar con sus 409; una descartada no se usa (otra versión, retoque, auditoría) ni entra en el contexto del `PROMPT_ARCHITECT`; candidatas y descartadas; visor y desplegable; portada |
| Navegador (aplicación local en simulación, copia de los datos) | ✅ Aspa en las 7 candidatas y no en la seleccionada; al descartar, «Descartados (1)» aparece cerrado; un clic en la descartada no la abre; el ✓ la devuelve y el desplegable desaparece; «Descartar» desde el visor muestra la seleccionada; igual en Composición y Render final |
| Playwright de extremo a extremo (aplicación local en simulación) | ✅ 7 passed (nuevo `test_e2e_discards.py`) |
| Postman CLI (backend local en simulación) | ✅ 53 peticiones, 95 comprobaciones |
| `mkdocs build --strict` | ✅ |
| pre-commit | ✅ |
| CI de la PR #61 | ✅ lint y tests, gitleaks, Docker con newman (colección con los descartes) y Playwright (7 pruebas, también la de los descartes), y la construcción de la documentación |

Coste real del paso: 0 €.

## 5. Estado final

⏳ En revisión — rama `feat/paso-43`.

## 6. Pendiente / futuro

- Paso 44: versión 4.1.0.
