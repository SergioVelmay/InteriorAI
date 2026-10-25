# Paso 24 — Estudio III: Render Final

## 1. Objetivo

Octavo paso del [plan de la versión 2.0.0](plan-version-2.md). La pestaña Render Final queda
completa. El modelo fotorrealista convierte la composición (o el render final actual) en una
fotografía realista, con cambios globales en texto libre, proporción y resolución, y con
«Otra versión» para repetir una imagen con el mismo prompt.

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Imagen de partida (B-055) | Dos botones, cada uno con la miniatura de su imagen: «Generar con la composición seleccionada» (siempre) y «Generar con el render final actual» (si hay uno seleccionado). Sustituye a la regla automática de B-051 |
| Entradas (B-051) | El renderizador recibe **solo la imagen de partida y el prompt**, sin referencias. Lo marcado en las fichas llega como texto al PROMPT_ENGINEER |
| Semilla (B-051) | La semilla de Azure no es reproducible (Paso 18): **sin campo de semilla**. «Otra versión» repite tal cual el prompt, la imagen de partida y la resolución de la imagen mostrada, sin indicaciones nuevas |
| Proporción y resolución (B-040) | 16:9, **3:2 (por defecto)**, 1:1, 2:3 y 9:16. Tres resoluciones por proporción, en múltiplos de 16 y con la proporción exacta: la mínima, igual o lo más parecida posible a la de los modelos GPT; la máxima (≤ 4 MP), por defecto; y la intermedia, en el punto medio del lado largo |
| Llamadas reales | Autorizadas sin confirmar cada una; avisar solo por encima de 1 € |

Resoluciones (`shared/sizes.py`):

| Proporción | Mínima | Intermedia | Máxima |
|------------|--------|------------|--------|
| 16:9 | 1536×864 | 2048×1152 | 2560×1440 |
| 3:2 | 1536×1024 | 2016×1344 | **2448×1632** |
| 1:1 | 1024×1024 | 1504×1504 | 1984×1984 |
| 2:3 | 1024×1536 | 1344×2016 | 1632×2448 |
| 9:16 | 864×1536 | 1152×2048 | 1440×2560 |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Modelo | `RenderRecord.variant_of_id` («Otra versión» de ese render final) |
| Render final | `generate_final(source="composicion" \| "render_final", variant_of)`. Recibe la imagen de partida y el prompt del PROMPT_ENGINEER; tamaño 2448×1632 por defecto. La variante repite el prompt sin volver a llamar al PROMPT_ENGINEER. Solo hay variantes de renders finales de la v2, porque los de la v1 dependían de entradas que ya no se envían. Las cadenas de la v1 (composición con brief) conservan su prompt y sus texturas |
| API | `FinalRequest`: `composition_id?`, `source`, `variant_of`, `size`, `extra_instructions` y `n`. Desaparecen `reference_ids` y `seed` |
| Prompt | `prompt_render_final.md` definitivo. Conserva la imagen sin añadir objetos, ni siquiera en la terraza. Los materiales visibles **no se regeneran**: se piden «exactamente como en la imagen» y se nombran con términos inequívocos («pile» y similares, prohibidos). Enriquece las indicaciones globales con lenguaje de fotografía e iluminación |
| Interfaz | Render Final, de arriba abajo: proporción y resolución (al cambiar la proporción, la máxima), indicaciones globales y los dos botones con su miniatura. A ancho completo, la galería y la imagen seleccionada; bajo «Seleccionar», «Otra versión» con su coste; después, el texto y lo enviado. Coste estimado por MP (`final_cost`): ≈ 0,079 € a 4 MP, sin confirmación |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 371 passed |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Postman en local (mock) | ✅ 53 peticiones, 96 comprobaciones |
| Playwright en local (mock) | ✅ 5/5 (render final, proporción 16:9, «Generar con el render final actual» y «Otra versión») |
| Render real desde la composición (FLUX, 2448×1632) | ✅ 26 s, 0,076 €. Primer intento: geometría fiel, pero la pana salió como bouclé y añadió una mesa en la terraza. Tras endurecer el prompt, pana fiel y nada añadido |
| «De noche» desde el render final actual | ✅ 29 s, 0,076 €. Exterior nocturno y luz interior cálida sin inventar lámparas (lo anota en las dudas). Con la regla de «no regenerar materiales», la pana se conserva |
| «Otra versión» | ✅ Mismo prompt, partida y tamaño (`variant_of_id`), sin llamada al PROMPT_ENGINEER. La variación entre versiones afecta también al tejido: sirve para elegir |
| CI de la PR #32 | ✅ lint y tests, gitleaks, Docker con newman y Playwright |

Hallazgo: sin las referencias, la fidelidad del tejido depende por completo del prompt. Describir
de nuevo un material ya visible hace que el modelo lo regenere, a veces mal. Pedir que se
conserve «exactamente como en la imagen» funciona mejor.

Coste real del paso: ≈ 0,38 € (5 renders de 4 MP).

## 5. Estado final

⏳ En revisión — rama `feat/paso-24`, PR #32.

## 6. Pendiente / futuro

- B-054: revisar juntos `prompt_render_final.md`.
- Paso 25: versión 2.0.0 (README con capturas, Gradio y Pillow 13, CHANGELOG y Release).
