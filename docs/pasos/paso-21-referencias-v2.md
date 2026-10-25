# Paso 21 — Referencias v2

## 1. Objetivo

Quinto paso del [plan de la versión 2.0.0](plan-version-2.md). La pestaña Referencias sustituye
a Assets. Cada imagen se analiza al subirla y produce una **receta** de ingredientes útiles
para el diseño. Su **ficha de casillas** guarda lo que el usuario quiere usar de ella. Incluye
el prompt de sistema de las recetas, la comparativa luna/sol y el reanálisis de las referencias
existentes.

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Formato de la receta | Grupos fijos y exhaustivos con un grupo **«Otros»** para lo no previsto (12 grupos). Cada elemento lleva texto, detalle y medidas con su origen: nota, cota de la imagen o **estimada** (siempre marcada así). Lo que piden las notas sale marcado y primero |
| Subida | **De una en una**: subir + anotar + analizar cada referencia. Análisis inmediato; si falla, la imagen se conserva y se puede volver a analizar |
| Notas editadas | «Volver a analizar con estas notas» rehace la receta y la ficha |
| Uso hasta el Paso 22 | El brief recibe lo marcado de las referencias activas. La imagen base es la primera activa con perspectiva marcada; si no hay, la regla anterior. El render final usa las activas salvo la base. Las inactivas no se usan. El usuario no subirá ni editará referencias hasta tener casi terminada la v2 |
| Referencias existentes | Se reanalizan conservando sus notas. A las capturas de la v1 se les añade «quédate con el punto de vista, la perspectiva y la geometría» y a los planos, «quédate con las medidas y la distribución». Las fichas antiguas se conservan como historia |
| Borrado | Sin «Mover a la papelera» en la interfaz: descartar = desmarcar todo. La API conserva el borrado |
| Llamadas reales | Autorizadas sin confirmar cada una; avisar solo por encima de 1 € en total |

Regla 6 de `AGENTS.md` actualizada: una medida estimada solo se admite marcada como tal y nunca
se trata como exacta.

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Modelo | `ReferenceRecipe` (12 grupos), `RecipeElement`, `ReferenceSheet` (receta + `selected`, activa si hay algo marcado) y `Asset.sheet`. La ficha de la v1 (`Asset.analysis`) queda como histórico |
| Prompt | `prompts/reference_analyst.md` reescrito: receta orientada por las notas, «Otros» sin dudar, medidas estimadas siempre marcadas. Para revisarlo juntos (B-054) |
| Pipeline | `reference_analyst.py`: `analyze_asset` (una imagen, con notas nuevas opcionales), `index_references` (en bloque: reanálisis), `save_sheet`; primer análisis de capturas y planos de la v1 con su papel en las notas |
| Uso | `sources.py`: referencias activas, imagen base, imágenes y fichas del brief, texturas del render final. Brief, auditoría y coste de la cadena leen las fichas nuevas |
| API | `POST /assets/{id}/analyze`, `PUT /assets/{id}/sheet` (sustituye a `PUT /assets/{id}/analysis`); `/references/index` analiza las que no tienen receta |
| Interfaz | Pestaña «Referencias»: subida única con notas, análisis al momento, ficha de casillas por grupo (grupo marcado = todos sus elementos), «Marcar todo», «Desmarcar todo», «Guardar ficha», «Volver a analizar». En el Estudio, las texturas por defecto son las activas que no son imágenes del espacio |
| Pruebas | Tests de API, pipeline y pestaña; Postman (49 peticiones); E2E de Referencias nueva y la de las demás pestañas con análisis al subir |

## 4. Comparativa luna/sol (B-052, llamadas reales)

Sobre una **copia** de los datos: recetas de 4 imágenes reales y el brief del Salón con las
fichas de sol.

**Recetas** (REFERENCE_ANALYST):

| Imagen | sol: tiempo · coste · elementos | luna: tiempo · coste · elementos |
|--------|--------------------------------|---------------------------------|
| Vista de SketchUp del salón | 59,7 s · 0,0435 € · 28 | 20,0 s · 0,0018 € · 19 |
| Planificador de IKEA | 29,5 s · 0,0167 € · 13 (los 6 módulos del sofá, uno a uno) | 15,3 s · 0,0010 € · 9 (el sofá como un solo elemento) |
| Inspiración JÄTTEBO | 58,3 s · 0,0364 € · 36 | 25,1 s · 0,0017 € · 30 |
| Alzado de la cocina | 40,1 s · 0,0229 € · 19 (cada módulo con su cota) | 16,8 s · 0,0012 € · 14 (electrodomésticos en «Otros») |

sol desglosa con más precisión y agrupa mejor: módulo a módulo, cotas por elemento y cada cosa
en su grupo. Cuesta unas 20 veces más (0,017-0,044 € por imagen) y tarda 2-3 veces más. Las dos
marcaron bien lo que pedían las notas.

**Brief** (PROMPT_ENGINEER): luna 19 s y 0,0016 €; sol 50 s y 0,0295 €. Los dos briefs son
correctos. El de sol es más minucioso (módulos, holguras, quitar cotas de la vista), pero tomó
las instrucciones de prueba «Comparativa luna/sol» como «día y noche» y pidió dos versiones.
Fue un fallo de la prueba, no del modelo.

**Recomendación:** mantener la asignación actual (fichas con sol, prompts con luna). Una receta
se hace una vez por imagen y su precisión alimenta todo lo demás. El brief se genera en cada
iteración y luna lo hace bien por una vigésima parte. **Decisión del usuario:** recetas con sol y prompts con luna (como en el `.env`).

## 5. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 358 passed |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Postman en local (mock, sobre una copia) | ✅ 49 peticiones, 87 comprobaciones |
| Playwright en local (mock) | ✅ 5/5 tras corregir las texturas por defecto del render final |
| Revisión visual con recetas reales de sol | ✅ ficha del planificador de IKEA con los 6 módulos marcados por las notas |
| CI de la PR #29 | ✅ lint y tests, gitleaks, Docker con newman y Playwright |

Coste real del paso hasta ahora: ≈ 0,16 € (recetas con sol 0,119 €, con luna 0,006 €, briefs
0,031 €). El reanálisis de las 7 referencias, tras el merge, costará unos 0,20 € con sol.

## 6. Estado final

✅ Cerrado — rama `feat/paso-21`, PR #29 revisada y mergeada por el usuario (asignación
aprobada: recetas con sol y prompts con luna). Docker reconstruido y las 7 referencias reales
reanalizadas con sol el 2026-10-25 (0,235 €): las dos fotos de la cocina sin notas quedaron
descartadas, como se acordó.

## 7. Pendiente / futuro

- B-054: revisar juntos el prompt de las recetas.
- Paso 22: el Estudio nuevo decide el uso de las selecciones; `legacy_kind` y la regla anterior
  de la imagen base desaparecen.
