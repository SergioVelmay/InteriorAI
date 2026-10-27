# Consejos

Lo que mejor funcionó en el caso del manual, etapa por etapa.

## La descripción del proyecto

La IA la lee **en cada generación**. Escríbela como un encargo a un interiorista:

- qué espacio es y desde dónde quieres verlo;
- los colores y materiales que ya tienes claros;
- de qué referencia sale cada cosa («las medidas salen del modelo 3D»);
- lo que **no** quieres («sin el desayunador»).

## Las notas de cada referencia

Las notas deciden qué se analiza y qué queda marcado en la ficha. Funcionan mejor así:

- **Una intención por referencia.** «Quédate solo con…» es más útil que una descripción de la
  imagen.
- **Di también qué ignorar.** «No uses su punto de vista ni sus colores» evita que un modelo 3D
  esquemático o una foto de otra casa se cuelen en el resultado.
- **Nombra lo que estorba.** En el caso, el desayunador del modelo de SketchUp se quitó en tres
  sitios: las notas de las dos imágenes del modelo («ignora el desayunador»), la descripción del
  proyecto y la auditoría manual. No apareció en ningún boceto.
- **Escribe las medidas que sepas.** Una medida en las notas o en una cota de la imagen se usa
  como exacta; la IA **no inventa medidas**. Lo que no conste se queda sin medida, y una medida
  estimada siempre va marcada como tal.

## Qué marcar en las fichas

- **Solo cuenta lo marcado.** Revisa la ficha tras el análisis y desmarca lo que contradiga a
  otras referencias (en el caso, la cocina blanca de la infografía).
- **Una sola imagen con la perspectiva marcada**: la de la vista que quieres. Si varias la marcan,
  la base es la primera activa.
- **Descarta lo que sobra.** Una referencia sin nada marcado no se envía; si otra ya aporta lo
  mismo, descártala en vez de duplicar.

## Las indicaciones

| Etapa | Para qué sirven | Ejemplo del caso |
|-------|-----------------|------------------|
| Bocetos | Orientar la tanda: luz, ambiente, lo que falte o sobre | «Salón sobrio, con el sofá y la alfombra en tonos arena y gris cálido» |
| Composición | Cambios concretos de mobiliario, colores y materiales | «Cambia las sillas mostaza por sillas de madera de roble con asiento tapizado en gris antracita» |
| Retoque | Lo que debe aparecer en la zona pintada, con su tamaño y material | «Un olivo de 1,5 m de alto, en una maceta cilíndrica de cerámica gris antracita mate» |
| Render final | Cambios globales: momento del día, luz, ambiente, personas | «De noche: cielo azul oscuro… luz cálida de unos 2700 K» |

- **Concreta colores y materiales** y relaciónalos con lo que ya hay: «en negro mate en lugar de
  dorado» combina mejor que «lámparas modernas».
- **Cierra con lo que no debe cambiar** cuando el cambio es pequeño: «No cambies nada más».
- **Lee «Lo que ha entendido la IA» y las dudas** de cada imagen: si algo no está claro, acláralo
  en las indicaciones de la siguiente generación.

## Elegir bien en cada etapa

- **Cada etapa parte de lo que eliges** en la anterior: no sigas con un boceto que no te convence;
  genera otra tanda.
- **La auditoría** compensa cuando el boceto se aleja del espacio real (medidas, distribución,
  elementos fijos). Para cambios de estilo o mobiliario bastan las indicaciones.
- **Retoca con margen** y de una zona cada vez. Para cambios en toda la imagen, genera sin
  retoque.
- **Otra versión** es la forma más barata de probar suerte con un render que casi está bien.

## Controlar el gasto

- Prueba la aplicación en **modo simulación** (`AI_PROVIDER_MODE=mock`): mismas pantallas, sin
  coste.
- La **calidad media** de bocetos y composiciones es un buen equilibrio; empieza con **4
  variantes**.
- Mira la **estimación** junto a cada botón: por encima de 0,20 € la aplicación pide confirmación.
- Revisa **Costes IA** de vez en cuando y contrasta con Azure Cost Management.

Como referencia, el caso completo (6 referencias, 8 bocetos, una auditoría, 3 composiciones y 5
renders) costó **1,57 €**.
