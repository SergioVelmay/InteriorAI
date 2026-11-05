# Paso 50 — La geometría en los prompts y el esquema como base

## 1. Objetivo

Cuarta parte de B-116. El [Paso 48](paso-48-laboratorio-geometria.md) midió que los modelos
abren el plano (la escena sale al 68–85 % de su tamaño) y el [Paso 49](paso-49-encuadre.md)
confirmó el desplazamiento. Este paso ataca las dos causas que sí están en nuestra mano:

1. **Lo que pedimos nosotros.** El prompt del render final pedía literalmente «gran angular
   moderado» y «verticales rectas»: le estábamos pidiendo al modelo justo lo que luego
   lamentábamos.
2. **Quién manda en la geometría.** El esquema 3D ya se enviaba a la composición, pero como un
   apoyo más entre doce. Nunca se había probado que fuese **la imagen que se edita**.

Todo el paso es **sin coste**: cambios de prompt e interfaz, validados en modo `mock`. La prueba
real queda pendiente de que el usuario ponga el `.env` en `azure`.

## 2. Decisiones (usuario, 2026-11-04)

| Tema | Decisión |
|------|----------|
| «Gran angular moderado» | Fuera, y repasar que no quede nada parecido en ningún prompt |
| El bloque IMPORTANTE | Preciso y completo, que no se escape nada: encuadre, zum, focal, campo de visión, perspectiva, punto de vista… |
| El esquema en la composición | Opcional, con una casilla por imagen, como las de auditoría y retoque |
| Dónde | Dos botones de Composición: a la izquierda, boceto y esquema; a la derecha, composición actual y esquema. Con una u otra o con las dos |
| Render final | Sin cambios: solo composición seleccionada y render actual, como ahora |

## 3. Lo que había (rastreo completo)

Se buscó en todo el repositorio cualquier cosa que empuje el encuadre (angular, focal, lente,
campo de visión, zum, amplio, espacioso, cámara, punto de vista…). Solo había dos sitios que lo
movieran de verdad, los dos en `prompt_render_final.md`:

| Dónde | Qué decía | Por qué importa |
|-------|-----------|-----------------|
| Punto 3 | «Óptica natural de fotografía de interiores: verticales rectas, **gran angular moderado**…» | Le pide abrir el plano, que es el defecto medido; y enderezar las verticales, que cambia la perspectiva cuando el esquema tiene tres puntos de fuga (ya se vio en el Paso 48) |
| Punto 6 | «Si la proporción de salida difiere…, pide **recomponer el encuadre** ampliando o recortando» | Legítimo al cambiar de proporción, pero daba permiso para reencuadrar |

El resto (`prompt_bocetos.md`, `prompt_composicion.md`) solo decía «conserva el encuadre y el
punto de vista», sin la fuerza necesaria.

## 4. Implementación

| Parte | Cambios |
|-------|---------|
| Los tres prompts de imagen | Bloque **IMPORTANTE** destacado antes de la lista de tareas: la cámara de la imagen base no se toca. Enumera encuadre y márgenes, escala (que cada elemento ocupe la misma parte del cuadro), distancia focal y ángulo de visión, posición de cámara (altura, distancia y posición lateral), dirección de mirada e inclinación, línea de horizonte, y tipo de perspectiva con sus puntos de fuga (si las verticales convergen, siguen convergiendo). Incluye la frase inglesa que debe abrir el prompt y prohíbe pedir abrir el plano, alejar la cámara, gran angular, enderezar verticales, recentrar o dejar aire alrededor |
| `prompt_render_final.md` | Fuera «gran angular moderado» y «verticales rectas»: de la óptica solo queda lo que no toca el encuadre (profundidad de campo y exposición). El punto 6 pasa a ser la única excepción, y acotada: al cambiar de proporción se recorta o se extiende por los bordes **manteniendo el tamaño y la posición de lo que ya se ve** |
| `pipelines/renders.py` | `generate_composition` admite `use_start` y `use_scheme`. El esquema sale siempre de los apoyos y se añade aparte, para que no se duplique y vaya por delante; ocupa una de las plazas de apoyo, así el número de imágenes (y el coste) no sube. Sin imagen de partida, el esquema va con el papel de **imagen base**: es lo que se edita. Papel nuevo `SCHEME_ROLE`: manda en encuadre, punto de vista y geometría, y de él no se toman materiales |
| API | `use_start` y `use_scheme` en `CompositionRequest`; 422 si no se marca ninguna |
| Interfaz | Bajo cada botón de Composición, sus dos miniaturas (imagen de partida y esquema 3D) y una casilla para cada una. Sin esquema en el proyecto, su casilla queda desmarcada y deshabilitada. La estimación de coste responde a lo que se marca |
| Cadena | La trazabilidad no se rompe: aunque solo se envíe el esquema, la composición sigue colgando del boceto que el usuario seleccionó |
| Manual | La tabla de controles de [Composición](../manual/composicion.md) explica las casillas nuevas |

Por defecto siguen marcadas las dos, de modo que el comportamiento es el de siempre salvo que el
esquema pasa a ir en segundo lugar en vez de perdido entre los apoyos.

## 5. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 386, con una prueba nueva en `test_api_renders.py`: con las dos imágenes el esquema va el segundo y se presenta como «esquema 3D del espacio»; sin esquema, no se envía; sin boceto, el esquema es la «imagen base» y la composición sigue colgando del boceto seleccionado; sin ninguna de las dos, 422 |
| Orden de entrada | ✅ Con los valores por defecto, la lista de imágenes es idéntica a la de antes del paso (el esquema ya era el primero de los apoyos) |
| Interfaz | ✅ La aplicación construye las cuatro casillas nuevas (`iai-use-draft`, `iai-use-scheme-draft`, `iai-use-current`, `iai-use-scheme-current`) |
| `ruff` y `mkdocs build --strict` | ✅ |
| CI de la PR #71 | ⚠️ A la primera falló el extremo a extremo: al añadir las dos opciones a `composition_body` se rompió la llamada del retoque, que seguía con la firma antigua y nunca llegaba a generar. Los tests unitarios no alcanzan ese camino; lo cazó Playwright. Arreglado separando las imágenes elegidas (`chosen_images`) del cuerpo común, que vuelve a su firma: el retoque no elige imágenes, porque edita la zona pintada |

Coste real del paso: 0 €.

## 6. Estado final

⏳ En curso — rama `feat/paso-50`.

## 7. Pendiente / futuro

- **La prueba real**, cuando el usuario ponga el `.env` en `azure`: una tanda de bocetos y una
  composición con cada combinación, midiendo con el Paso 49 y comparando con el laboratorio
  (bocetos 43–54 % a ±8 px, composiciones 43–53 %). Unos 0,60 € en total, anunciando antes cada
  llamada.
- B-117: el multiplicador de zum del encuadre.
