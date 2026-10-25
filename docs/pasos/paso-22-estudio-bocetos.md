# Paso 22 — Estudio I: base común y Bocetos

## 1. Objetivo

Sexto paso del [plan de la versión 2.0.0](plan-version-2.md). El Estudio pasa a tener tres
pestañas (Bocetos, Composición y Render Final) que se desbloquean en orden. Comparten una base
común: maquetación 50/50, imagen grande con «Ver más» y confirmación junto al botón. La pestaña
Bocetos queda completa. El brief de la v1 desaparece: cada generación escribe su propio prompt.

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Brief | **Se sustituye por un prompt automático por generación**. Al pulsar «Generar», el PROMPT_ENGINEER (luna) escribe el prompt de esa generación con sus entradas reales (descripción, imágenes con su papel, lo marcado en las fichas e indicaciones) y explica lo que ha entendido y sus dudas, que se guardan con cada imagen. Sin aprobación aparte: el clic es la aprobación. Los briefs antiguos se conservan en los datos y las imágenes de la v1 los citan |
| Calidad de los bocetos | **Media** por defecto (B-040 se contradecía) |
| Imágenes del boceto | La referencia activa con perspectiva marcada es la imagen base y las demás activas son apoyos (hasta 6). Sin perspectiva, el modelo compone libremente |
| Composición y Render Final | Llevan los controles actuales (retoque y auditoría incluidos) hasta los Pasos 23 y 24 |
| Prompts de sistema (B-054) | Los escribe Claude, los prueba con llamadas reales y se revisan juntos en la PR |
| Idea nueva para los Pasos 23 y 24 | **B-055**: dos botones de generar, cada uno con la miniatura de su imagen de partida (ver el backlog) |
| Llamadas reales | Autorizadas sin confirmar cada una; avisar solo por encima de 1 € |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Modelo | `StagePrompt` (prompt, interpretación, dudas); `RenderRecord.prompt_info` y `prompt_version`; `brief_id` y `brief_version` opcionales (histórico) |
| Prompt automático | `pipelines/prompt_writer.py`: contexto con el papel de cada imagen y solo lo marcado; prompts de sistema `prompt_bocetos.md` (trabajado a fondo: enriquece las notas breves con lenguaje de interiorismo, luz y criterio estético) y `prompt_composicion.md` / `prompt_render_final.md` (provisionales) |
| Bocetos | `generate_drafts` sin brief: imagen base (perspectiva) + apoyos, 1-8 variantes (4), calidad media, formato 1536x1024 (3:2) por defecto; 422 si no hay referencias activas |
| Composición y render final | Con prompt automático en las cadenas nuevas y con el brief en las de la v1; la auditoría funciona sin brief (usa lo marcado en las fichas) |
| Interfaz | Estudio en tres pestañas: «Composición» se activa con un boceto seleccionado y «Render Final» con una composición seleccionada (B-043). Bocetos: referencias activas arriba, controles (calidad y formato; variantes; indicaciones) y miniaturas 2 por fila a la izquierda (B-042), imagen grande con «Seleccionar» y «Ver más» (lo que entendió la IA, dudas, prompt, coste de la cadena y miniaturas de lo enviado, B-047) a la derecha. Confirmación «Pendiente de confirmar» debajo del botón, con el botón desactivado mientras tanto (B-049). Umbral: 0,15 € |
| Corrección | El editor de retoques se vuelve a montar al abrir su pestaña o su desplegable: montado oculto, enviaba el fondo truncado |
| API | `/renders/drafts`: n 1-8 (4), calidad media; el resto sin cambios. Los endpoints de briefs siguen, sin uso en la interfaz |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 358 passed |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Postman en local (mock) | ✅ 49 peticiones, 87 comprobaciones |
| Playwright en local (mock) | ✅ 5/5 (Estudio en tres pestañas, retoque en Composición) |
| Bocetos reales (script, copia del Salón) | ✅ 4 en calidad media en 32 s: 0,001 € el prompt (luna, 9,7 s) y 0,142 € la imagen (flare). Conservan la vista, el JÄTTEBO por módulos y la pana verde oliva |
| Bocetos reales por la interfaz (Azure, copia) | ✅ 5 bocetos: confirmación junto al botón (≈ 0,158 €) y resultado real 0,178 €, con las indicaciones aplicadas (luz de atardecer, planta junto a la terraza) |
| CI de la PR #30 | ✅ lint y tests, gitleaks, Docker con newman y Playwright |

Hallazgo de costes: en los bocetos pesan más las **imágenes de entrada** (≈ 0,042 € cada una, en
tokens de imagen) que los bocetos (≈ 0,009 € cada uno en calidad media). Con 3 referencias
activas, 4 bocetos cuestan ≈ 0,16 € y piden confirmación; con 1 o 2, no.

El modelo añade a veces elementos no pedidos (alfombras, mesas de centro), aunque el prompt lo
desaconseja. Se revisará con los prompts.

Coste real del paso: ≈ 0,32 €.

## 5. Estado final

✅ Cerrado — rama `feat/paso-22`, PR #30 revisada y mergeada por el usuario. Docker
reconstruido. El usuario revisó y aprobó los prompts de bocetos y de recetas, y subió el umbral
de confirmación a 0,20 € (aplicado en el [Paso 23](paso-23-composicion.md)).

## 6. Pendiente / futuro

- Pasos 23 y 24: Composición y Render Final definitivos, con B-055.
- B-054: revisar juntos `prompt_bocetos.md`; los de composición y render final, en sus pasos.
- Decidir si el umbral de 0,15 € encaja con el coste real de las imágenes de entrada.
