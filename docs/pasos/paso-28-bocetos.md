# Paso 28 — Bocetos

## 1. Objetivo

Tercer paso del [plan de la versión 3.0.0](plan-version-3.md): la pestaña Bocetos a ancho
completo y unos prompts que no copien lo que el usuario no marcó, no dibujen las anotaciones de
las referencias y den bocetos realistas y minimalistas (B-067 a B-070).

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Exclusiones (B-068) | Por el prompt: el PROMPT_ARCHITECT recibe, de cada imagen que se envía, lo NO marcado de su receta, y lo nombra como «no tomar»; estancia limpia por defecto. Plan B (no enviar como imagen las referencias de solo color o material, describirlas en texto) solo si las pruebas reales lo pedían: no ha hecho falta |
| Anotaciones (B-069) | Rótulos, cotas, medidas, marcas y líneas auxiliares: se usa la información, nunca se dibujan (bocetos, composición y render final) |
| Estilo (B-070) | Bocetos realistas y minimalistas: fuera «clean colored concept sketch» |
| Llamadas reales | Autorizadas sin confirmar cada una; avisar solo por encima de 1 € |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Bocetos a ancho completo (B-067) | De arriba abajo y al 100 %: referencias activas; Calidad y Formato; Variantes, Indicaciones, botón y coste; galería de 4 por fila; el boceto en su proporción con «Seleccionar» y toda la información debajo, sin desplegable. `_viewer` queda con una sola forma (sin acordeón) para las tres pestañas |
| Contexto del prompt (B-068) | `ReferenceSheet.unselected_elements()`; `references_section` añade `ignorar` (lo no marcado, por grupos) a las referencias que se envían como imagen |
| `prompt_bocetos.md` (B-068, B-069, B-070) | «Solo lo marcado», con qué tomar y qué NO tomar de cada imagen; estancia limpia por defecto; anotaciones sin dibujar (y nunca «keep the dimensions in their traced location»); imagen realista y minimalista, sobria como un render de catálogo |
| `prompt_composicion.md` | Las mismas exclusiones por imagen (lista `ignorar`) y la regla de las anotaciones |
| `prompt_render_final.md` | La regla de las anotaciones de las fichas |
| Nombres de la v1 (petición del usuario en la PR) | Los últimos archivos con nombres de roles anteriores, exclusivos de la v1, pasan a nombrarse por lo que hacen: `prompt_engineer.py` → `brief_v1.py`, `prompts/prompt_engineer.md` → `prompts/brief_v1.md` y `prompts/geometric_auditor.md` → `prompts/auditor_captura_v1.md`. Los `prompt_version` ya guardados conservan el nombre anterior (son historia) |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 382 passed |
| `uv run ruff check .` / `ruff format --check` / pre-commit | ✅ |
| Postman en local (mock) | ✅ 53 peticiones, 96 comprobaciones |
| Playwright en local (mock) | ✅ 6/6 |
| Bocetos reales (FAST_DRAFT_MAKER, copia de «Personalización Cocina Los Molinos», 4 referencias activas) | ✅ 4 en calidad media en 51 s, 0,192 €. Con los prompts del Paso 22, los bocetos copiaban de la infografía el sofá, la mesa con sillas, las lámparas y las flores, y uno dibujaba las cotas rojas; ahora, cocina limpia con solo lo marcado (incluidas las cortinas, que sí estaban marcadas) y sin anotaciones. Comparación en `InteriorAI-capturas/etapa-06-paso-28/` (fuera del repositorio) |
| CI de la PR #40 | ✅ lint y tests, gitleaks, Docker con newman y Playwright |
| Composición real con el primer boceto (COMPOSITION_BUILDER) | ✅ 42 s, 0,060 €: limpia, sin la tostadora, las plantas ni la vajilla de la referencia de materiales y sin los colores de marcado del esquema |

Coste real del paso: ≈ 0,25 €.

## 5. Estado final

⏳ En revisión — rama `feat/paso-28`, PR #40.

## 6. Pendiente / futuro

- B-054: revisar juntos los cambios de `prompt_bocetos.md`, `prompt_composicion.md` y
  `prompt_render_final.md`.
- Paso 29: Composición y Render Final.
