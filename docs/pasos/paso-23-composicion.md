# Paso 23 — Estudio II: Composición

## 1. Objetivo

Séptimo paso del [plan de la versión 2.0.0](plan-version-2.md). La pestaña Composición queda
completa: auditoría opcional del boceto seleccionado, retoque con máscara de la composición
seleccionada y creación de la composición a partir del boceto o de la composición actual. Además,
la pestaña «Estudio» desaparece: Bocetos, Composición y Render Final pasan a ser pestañas de
primer nivel.

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Pestañas | **Sin pestaña «Estudio»**: Proyectos, Referencias, Bocetos, Composición, Render Final y Costes IA. Composición y Render Final siguen bloqueadas hasta haber selección en la etapa anterior |
| Auditoría (B-046) | Del **boceto seleccionado**, frente a **todas** las referencias activas que marcan perspectiva o geometría (ninguna, una o varias), con lo marcado en las fichas como lista de comprobación; se muestran las miniaturas que se comparan. Notas del usuario como «auditoría manual» |
| Retoque (B-038) | **Nunca un parche**: la máscara solo indica dónde actuar y se guarda la imagen completa del modelo. Se aplica al pulsar «Generar con la composición actual» con «Usar el retoque» marcado; el prompt también lo escribe el PROMPT_ENGINEER |
| Apoyos | **Hasta 12** imágenes de apoyo además de la de partida (OpenAI documenta 16 por edición), primero las de perspectiva y geometría y después por antigüedad. Las que no caben se ven con el **pie en rojo** y se avisa en Referencias |
| Maquetación | Bocetos en 50/50, con la imagen a la derecha a ancho de columna y **altura según su proporción**. Composición y Render Final: controles arriba y, a ancho completo, la galería, la imagen seleccionada en su proporción, el texto (interpretación, dudas, prompt) y las miniaturas de lo enviado |
| Ficha de la referencia | **Solo nombres**; el detalle y las medidas, en un tooltip al pasar el ratón |
| Umbral de confirmación | **0,20 €** (antes 0,15 €), a ajustar con el uso |
| Llamadas reales | Autorizadas sin confirmar cada una; avisar solo por encima de 1 € |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Reglas de entrada | Nuevo `shared/supports.py`, compartido por backend e interfaz: referencias activas, imagen base de los bocetos, referencias del espacio (`geometric_references`), apoyos por prioridad y `split_supports` (los que se envían y los que quedan fuera, `MAX_SUPPORTS = 12`). `ImageEditRequest` admite hasta 16 imágenes; el renderizador sigue limitado a 8 |
| Composición | `generate_composition(source="boceto" \| "composicion", use_audit, audit_notes)`: la imagen de partida (boceto seleccionado o composición seleccionada) más los apoyos; 1536x1024 (3:2) por defecto. Con «Usar la auditoría», el PROMPT_ENGINEER recibe la última auditoría con IA del boceto y las notas del usuario. Las cadenas de la v1 (con brief) siguen igual |
| Retoque | `inpaint_render` recibe también las indicaciones y la auditoría; el PROMPT_ENGINEER escribe el cambio (sección «Modo retoque» con la instrucción y los límites de la zona) y el modelo recibe la composición, la máscara y los apoyos. Se guardan `prompt_info` y `prompt_version` |
| Auditoría | `AUDITABLE` incluye los bocetos; las imágenes nuevas se comparan con todas las referencias del espacio (prompt `auditor_espacio.md`) y las de la v1, con su captura (`geometric_auditor.md`). `RenderAudit.reference_asset_ids` y `notes`; `reference_asset_id` queda para la v1. El endpoint acepta `{notes}` |
| Prompts | `prompt_composicion.md` definitivo (partida, apoyos, correcciones de auditoría y modo retoque) y `auditor_espacio.md` nuevo (cita las referencias por su nombre en las correcciones) |
| API | `CompositionRequest`: `source`, `use_audit`, `audit_notes`; `POST /audit` con `{notes}`; `/inpaint` con `extra_instructions`, `use_audit` y `audit_notes` |
| Interfaz | `build_studio_tabs` crea las tres pestañas en la barra principal. Composición, de arriba abajo: ① auditoría (miniaturas comparadas, observaciones, «Auditar con IA» e informe); ② retoque (editor sobre la composición seleccionada e instrucción); ③ crear (calidad, formato, «Usar la auditoría», «Usar el retoque», indicaciones, apoyos que se envían y dos botones con la miniatura de su imagen de partida: «Generar con el boceto seleccionado» y «Generar con la composición actual»); galería e imagen a ancho completo. Render Final sin auditoría. Composición y Render Final se desbloquean al cambiar de proyecto, sin tener que abrir Bocetos |
| Editor (B-039) | Rojo fijo sin el control de paleta y el icono de tamaño como dos circunferencias concéntricas (CSS sobre controles internos de Gradio; lo comprueba el E2E). La máscara se guarda con el evento `input` del editor (`change` no se emite al pintar) |
| Referencias | Casillas con el nombre; el detalle va al `title` de cada casilla (contenedor oculto `#iai-sheet-tips` y un `MutationObserver` en el JS de la aplicación). Aviso si hay referencias activas que no caben |
| Corrección | Los `gr.State` comunes se crean dentro de una pestaña: como hijos directos de `gr.Tabs`, Gradio duplicaba en la barra la pestaña seleccionada |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 366 passed |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Postman en local (mock) | ✅ 50 peticiones, 91 comprobaciones |
| Playwright en local (mock) | ✅ 5/5 (pestañas de primer nivel, auditoría del boceto, composición con la auditoría y con la composición actual, retoque, tooltips de la ficha, editor sin paleta) |
| Auditoría real del boceto (astra, `medium`, copia del Salón) | ✅ 27 s, 0,136 €: comparado con las dos referencias del espacio, 91/100; comprobó las observaciones (tres reposacabezas, chaise a la derecha) y propuso corregir el encuadre |
| Composición real con la auditoría (sunburst, 4 imágenes de entrada) | ✅ 30 s, 0,047 € (prompt incluido): conserva el boceto y aplica la corrección de encuadre |
| Retoque real (planta en una zona del 18 x 62 %) | ✅ 30 s, 0,047 €: la planta queda dentro de la zona y el resto, intacto; imagen completa del modelo |

Hallazgo de costes: el STRUCTURAL_COMPOSER cobra mucho menos por imagen de entrada que el
modelo de bocetos (≈ 0,010 € frente a 0,042 €): una composición con 4 imágenes cuesta ≈ 0,05 €.
La estimación de la interfaz se ha ajustado (`composition_cost`).

Coste real del paso: ≈ 0,23 €.

## 5. Estado final

⏳ En revisión — rama `feat/paso-23`.

## 6. Pendiente / futuro

- Paso 24: Render Final definitivo (B-055 para el render, B-040 y B-051 con FLUX).
- B-054: revisar juntos `prompt_composicion.md` y `auditor_espacio.md`.
- Ajustar el umbral de 0,20 € con el uso.
