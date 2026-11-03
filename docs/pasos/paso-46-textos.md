# Paso 46 — Cuadros de texto

## 1. Objetivo

B-115, observación del usuario: envió por error unas indicaciones que eran para otra imagen. El
texto de un retoque seguía ahí al retocar otra composición, y le pareció que también entre
proyectos. Analizar todos los cuadros de texto en todas las situaciones, probarlos y mejorar la
experiencia sin perder lo escrito: que quede asociado a cada imagen.

Primer paso tras la 4.1.0; la versión llegará cuando se agrupen más arreglos (decisión del
usuario).

## 2. Análisis

| Cuadro | Antes |
|--------|-------|
| Nuevo proyecto (nombre y descripción) | Se vaciaba al crear (Paso 41) ✅ |
| Proyecto activo (nombre y descripción) | Se cargaba de cada proyecto ✅ |
| Referencias: notas al subir | Se vaciaban al subir o cancelar (Paso 41) ✅ |
| Referencias: notas de cada referencia | Se cargaban de cada referencia ✅ |
| Bocetos: indicaciones | **Nunca se vaciaba**: ni al generar, ni al cambiar de imagen o de proyecto |
| Composición: observaciones de la auditoría | **Nunca se vaciaba**; y con «Usar la auditoría» la composición enviaba lo que hubiera en el cuadro, aunque fuera de otro boceto o de otro proyecto |
| Composición: cambio en la zona pintada | **Nunca se vaciaba**: al elegir otra composición, el editor se vaciaba pero la instrucción no (el caso del usuario) |
| Composición: indicaciones | **Nunca se vaciaba** |
| Render final: indicaciones | **Nunca se vaciaba** |
| «Usar la auditoría», «Usar el retoque» | Conservaban su estado al cambiar de proyecto; «Usar el retoque» seguía marcado tras retocar |

Comprobado en el navegador (simulación, copia de los datos): tras escribir en todos y generar, y
tras cambiar a otro proyecto, el texto seguía en los cinco. Al recargar la página sí se vacían:
es el estado de la pestaña, no una caché del navegador.

Además, de lo escrito solo se guardaban la instrucción del retoque y las observaciones de cada
auditoría; las indicaciones de bocetos, composiciones y renders no quedaban con la imagen.

## 3. Decisiones (usuario, 2026-11-03)

| Tema | Decisión |
|------|----------|
| Al enviar | El cuadro se vacía al enviarse con éxito; con error o cancelando la confirmación, se conserva para reintentar |
| Al cambiar de proyecto | Se vacían los textos y se desmarcan «Usar la auditoría» y «Usar el retoque»; la calidad, el formato, las variantes, la proporción y la resolución se conservan |
| Observaciones de la auditoría | Ligadas a su boceto: se vacían al seleccionar otro; «Usar la auditoría» toma lo guardado en la última auditoría más lo que se escriba entonces |
| Lo escrito | Guardado con cada imagen y visible en su trazabilidad |
| Versión | Más adelante, agrupando más arreglos |

## 4. Implementación

| Parte | Cambios |
|-------|---------|
| Modelo | `RenderRecord.indications` (por defecto vacío: los datos anteriores se leen tal cual) |
| Backend | Bocetos, composiciones, renders finales y retoques guardan las indicaciones tal cual; «Otra versión» hereda las de la original; `audit_corrections` añade las observaciones guardadas con la última auditoría |
| Trazabilidad | «Tus indicaciones: «…»» con cada imagen; «Tus observaciones: «…»» en el informe de la auditoría |
| Vaciar al enviar | `execute` añade `sent(action)`: el cuadro de la acción enviada con éxito (bocetos, auditoría, composición, render final; en un retoque, también su instrucción y «Usar el retoque») |
| Vaciar al cambiar | `text_project` (proyecto de los textos) y `selected_draft` disparan su `.change`: textos y casillas al cambiar de proyecto; observaciones al cambiar de boceto |
| Cuadros editables | `interactive=True` en los cinco: al ser también salidas, Gradio los dejaba de solo lectura (el del retoque se lee en un evento creado dentro del editor dinámico) |
| Documentación | Manual (portada, Bocetos y Composición), referencia (datos e interfaz), `docs/agent/` y esquema OpenAPI |

## 5. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ Tests nuevos: indicaciones guardadas en bocetos, composiciones, renders, «Otra versión» y retoques; observaciones de la auditoría en la composición; trazabilidad e informe; eventos que vacían los textos al cambiar de proyecto o de boceto |
| Playwright de extremo a extremo (aplicación local en simulación) | ✅ 8 passed, dos veces. Nuevo `test_e2e_texts.py`: tras generar, el cuadro vacío y «Tus indicaciones» en la trazabilidad; tras auditar, las observaciones en el informe; lo escrito sin enviar no pasa a otro proyecto (cambiando desde la galería, sin recargar) y «Usar la auditoría» se desmarca. En el retoque: instrucción vacía y «Usar el retoque» desmarcado tras enviarlo |
| `mkdocs build --strict` | ✅ |
| pre-commit | ✅ |

Coste real del paso: 0 €.

## 6. Estado final

⏳ En revisión — rama `feat/paso-46`.
