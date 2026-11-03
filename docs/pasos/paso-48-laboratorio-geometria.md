# Paso 48 — Laboratorio de geometría

## 1. Objetivo

Segunda parte de B-116: probar, con la medida del Paso 47, qué acerca bocetos, composiciones y
renders a la geometría del esquema 3D de SketchUp, **sin postproducción** (decisión del usuario:
análisis sí, retocar las imágenes no). Presupuesto: hasta 5 €.

## 2. Montaje

- Copia del proyecto «Diverso Getafe 3 5B Cocina y Sofá Jattebo» en la aplicación del usuario:
  **«Laboratorio geometría · Cocina y Sofá Jattebo»**, con sus 10 referencias, notas y fichas,
  creada con el repositorio de la aplicación (sin IA). Se conserva para que el usuario la vea.
- Medida: fidelidad al esquema (aristas que coinciden a ±3 / ±8 px); el esquema contra sí mismo
  da 92 % / 94 %.
- Punto de partida, en el proyecto original: bocetos del 37 % al 49 % a ±8 px; render final
  seleccionado, 40 % (un candidato, 59 %).

## 3. Resultados

| Prueba | Qué | Fidelidad a ±8 px | Coste |
|--------|-----|-------------------|------:|
| L1 | 4 bocetos como hoy (sin indicaciones) | 54 %, 47 %, 50 %, 49 % (media 50 %) | 0,46 € |
| L2 | 4 bocetos con la geometría estructurada en las indicaciones: cámara fija y posición de cada volumen en % del ancho y del alto, sacada de los colores planos del esquema | 54 %, 51 %, 48 %, 43 % (media 49 %) | 0,47 € |
| L3 | Bocetos con `input_fidelity="high"` (máxima fidelidad a la imagen de entrada) | El modelo de bocetos **no lo admite** (400): solo se cobró el prompt | ≈ 0,003 € |
| L4 | Composición desde el mejor boceto (54 %), sin y con la geometría en las indicaciones | 51 % y 52 % | 0,26 € |
| L5 | Render final desde esa composición, sin y con la geometría en las indicaciones | 47 % y 51 % | 0,17 € |
| **Total** | 14 llamadas | | **1,36 €** |

## 4. Conclusiones

1. **Describir la geometría en el prompt no la fija.** Con coordenadas de cada volumen y la cámara
   explícita, la media de los bocetos no cambia (49 % frente a 50 %); en el render final, +4
   puntos, dentro de lo que varía de una imagen a otra.
2. **La geometría se pierde en el primer paso**, al convertir el esquema en boceto (≈ 50 % a
   ±8 px). Composición y render final la mantienen casi igual (−2 a −5 puntos): la cadena no
   empeora mucho; el problema es de partida.
3. **Dentro de una misma tanda hay diferencias de hasta 11 puntos** (43 % a 54 %), y en el
   proyecto original un render candidato llegaba al 59 % frente al 40 % del seleccionado. Elegir
   con la medida es la mejora más barata y segura; ocho bocetos cuestan casi lo mismo que cuatro
   (lo que pesa son las imágenes de entrada).
4. **Coincidir al píxel no es alcanzable** con estos modelos y sin postproducción: reinterpretan
   la escena aunque reciban el esquema como base, y la opción de máxima fidelidad a la imagen no
   está disponible en el de bocetos.

### Segunda prueba: el esquema a dos puntos de fuga

Observación del usuario: los renders convertían las vistas picadas (tres puntos de fuga) en vistas
de dos puntos, con las verticales paralelas. Parte de la causa estaba en el prompt de sistema del
render final, que pide «verticales rectas»; además, los modelos tienden a enderezarlas. El
usuario sacó la misma vista en SketchUp con la perspectiva de dos puntos (campo de visión
vertical de 50°, ≈ 26 mm) y se repitió la cadena en una segunda copia, **«Laboratorio geometría
2 · Cocina y Sofá Jattebo (dos puntos de fuga)»**, con solo la base cambiada (analizada de nuevo
con sus notas):

| Prueba | Fidelidad a ±8 px | Coste |
|--------|-------------------|------:|
| Análisis de la base nueva | — | 0,05 € |
| 4 bocetos como hoy | 41 %, 44 %, 43 %, 40 % (media 42 %) | 0,46 € |
| Composición desde el mejor | 43 % | 0,13 € |
| Render final | 43 % | 0,09 € |
| **Total** | 7 llamadas | **0,73 €** |

Las verticales ya coinciden y la cadena no pierde geometría, pero la superposición muestra la
causa principal de la diferencia: **el modelo aleja la cámara** (como con un objetivo más
angular): toda la escena sale más pequeña y desplazada hacia arriba y a la izquierda. No es que
cada volumen esté mal dibujado; hay un zum y un desplazamiento globales.

### Tercera prueba: dos puntos de fuga y focal de 60 mm en SketchUp

Copia **«Laboratorio geometría 3 · Cocina y Sofá Jattebo (dos puntos, 60 mm)»**, con la vista
sacada en SketchUp con perspectiva de dos puntos y focal de 60 mm (encuadre más cerrado):

| Prueba | Fidelidad a ±8 px | La escena sale al | Coste |
|--------|-------------------|-------------------|------:|
| Análisis de la base | — | — | 0,06 € |
| 4 bocetos | 53 %, 43 %, 44 %, 51 % (media 48 %) | 68–76 % | 0,46 € |
| Composición desde el mejor | 53 % | 75 % | 0,13 € |
| Render final | 50 % | 85 % | 0,09 € |

Mejor que la vista a 50° (42–43 %) y parecida a la picada (50–52 %). Los modelos siguen sacando
la escena más pequeña (al 68–85 % de su tamaño en el esquema) y desplazada: con cualquier
encuadre, abren el plano. Ajustado ese zum, el error medio de las aristas baja a 6–8 px.

Total del laboratorio: **2,83 €** (de 5 € autorizados).

## 5. Opciones para seguir (para decidir)

| Opción | Qué | Coste |
|--------|-----|-------|
| A | Usar la fidelidad para elegir: ordenar o destacar la más fiel de cada tanda, y recomendar tandas de 8 | Sin coste |
| B | Componer **directamente desde el esquema** (sin pasar por un boceto), probando si el modelo de composición admite la máxima fidelidad sin máscara | Unos 0,15 € de prueba |
| C | Un modelo con **control estructural** (aristas o profundidad, tipo ControlNet), si el catálogo de Azure AI Foundry del usuario lo ofrece: es lo que fija la geometría por construcción | Depende del modelo; el usuario tendría que desplegarlo |

## 6. Validación

Laboratorio: medidas con `ui/geometry.py` (Paso 47) sobre las imágenes generadas. La opción
experimental `input_fidelity` se probó en una rama de trabajo y se retiró del código al ver que
el modelo de bocetos la rechaza: el paso solo deja este documento.

Coste real del paso: 2,83 € (1,36 €, 0,73 € y 0,74 € de las tres pruebas; por debajo de los 5 €
autorizados; se avisó al pasar de 1 €).

## 7. Estado final

⏳ En revisión — rama `feat/paso-48`.
