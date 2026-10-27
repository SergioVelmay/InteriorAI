# Plan de acción — InteriorAI 4.0.0

Propuesto el 2026-10-27, tras publicar la 3.0.0. Reúne los prompts más precisos del Paso 32
(B-054, B-094 a B-097, ya hechos), la retirada de la compatibilidad con la v1 (B-056), la
documentación pública en GitHub Pages (manual de usuario y referencia técnica, B-099 a B-101),
los estándares de comunidad de GitHub (B-102) y la actualización de precios y costes con la
factura real de Azure (B-098). Ampliado el mismo día a petición del usuario (Pasos 34 a 39) y, tras el manual, con los
arreglos de la interfaz que salieron en él (Paso 38; precios y versión pasan a 39 y 40).

## Por qué 4.0.0

Retirar la v1 quita endpoints (`/briefs`) y campos de la API y del modelo de datos (esquema v3,
con migración automática). Según SemVer, un cambio incompatible es una versión mayor, como en la
2.0.0 y la 3.0.0 (decisión del usuario, 2026-10-27). Los datos de la 1.0.0 dejan de leerse:
quien venga de ella actualiza antes a la 3.0.0.

## Pasos

| Paso | Contenido | Entradas | Llamadas reales |
|------|-----------|----------|-----------------|
| 32. Prompts del PROMPT_ARCHITECT ✅ | Criterios comunes, más contexto, imágenes con detalle alto, tope de salida y timeout propio | B-054, B-094 a B-097 | 0,38 € (hecho) |
| 33. Retirar la compatibilidad con la v1 ✅ | Esquema v3 con migración automática (copia en `metadatos.v2.json`, también al restaurar de la papelera): las imágenes de la v1 quedan como imágenes sueltas, sin su cadena; las referencias con tipo antiguo, como referencias normales. Fuera los briefs (endpoints, pipeline, prompt y estados), las cadenas de la v1 en composición y render final, la auditoría frente a la captura, el puente `legacy_kind`, la migración desde la 1.0.0, el coste de cadena de la v1 y los textos de la v1 en la interfaz, Postman y tests | B-056 | No |
| 34. Web de documentación ✅ | MkDocs Material publicado en GitHub Pages con una GitHub Action (construcción estricta en cada PR, publicación al mergear en `main`). Estructura completa; inicio, instalación y configuración; versiones (CHANGELOG y Releases), seguridad y licencia | B-099 | No |
| 35. Referencia técnica ✅ | Arquitectura; API con Swagger interactivo a partir del OpenAPI de FastAPI; modelo de datos y almacenamiento; IA, roles y costes; desarrollo (tests, CI, bitácora) | B-100 | No |
| 36. Manual de usuario ✅ | Caso completo «Cocina Abierta para Manual de Usuario» desde cero en la aplicación real (modo `azure`), pasando por todas las opciones; capturas de cada pestaña y de cada sección en cada estado (vacía, rellena, procesando, resultado); una guía por pestaña y consejos | B-101 | 1,57 € (hecho) |
| 37. Comunidad del repositorio ✅ | `CONTRIBUTING.md`, código de conducta, plantillas de issues y de PR, temas y web en la descripción del repositorio, Wiki desactivada (la documentación vive en la web) | B-102 | No |
| 38. Arreglos de la interfaz | Lo que salió al hacer el manual: la estimación junto a cada botón sigue las variantes, la calidad y la resolución (B-104); aviso exacto sobre el coste de las llamadas con error (B-105); el detalle de una llamada en Costes IA se oculta al hacer clic fuera del registro (B-106, observación del usuario) | B-104 a B-106 | No |
| 39. Precios y costes reales | Contraste de la estimación con la factura real de Azure de los últimos días, incluido el gasto del Paso 36 (como el mantenimiento de octubre): `config/pricing.yaml`, factor de facturación y costes orientativos del README. El usuario aporta los datos de Azure Cost Management. | B-098 | No |
| 40. Versión 4.0.0 | README, CHANGELOG (nota de actualización: datos de la 1.0.0 vía la 3.0.0), versión en los `pyproject.toml`, etiqueta y Release con el OK del usuario | — | No |

## Decisiones tomadas (usuario, 2026-10-27)

1. **Imágenes de la v1 de los datos reales** (los dos proyectos de prueba): se conservan como
   imágenes sueltas, sin la cadena de la v1 (brief, rechazos, salidas en bruto de los retoques).
2. **Datos de la 1.0.0** (esquema 1): dejan de leerse; se quita la migración v1 → v2.
3. **Versión 4.0.0**, con los prompts del Paso 32 y la actualización de precios.

4. **Documentación** (2026-10-27): GitHub Pages con MkDocs Material (no la Wiki), solo en
   español, sin versiones de la documentación (una página de versiones con el CHANGELOG y las
   Releases). Capturas en JPEG o WebP de menos de 1 MB (el repositorio crecerá unos 15-20 MB).
   GitHub Pages lo activa Claude.

## Caso del manual (Paso 36, brief del usuario)

Proyecto nuevo **«Cocina Abierta para Manual de Usuario»**, con las referencias de
«Personalización Cocina Los Molinos», hecho desde cero en la aplicación real:

- **Punto de vista y perspectiva:** los de la infografía con muchos muebles (la vista general),
  no los de las capturas de SketchUp.
- **Capturas de SketchUp:** solo las medidas y la distribución de los elementos, sin el
  desayunador que está delante del cuerpo principal de la cocina.
- **Referencias de cocina:** los colores, gris antracita y madera.
- **Render del espacio abierto vacío:** los materiales de paredes, suelo y techo, las ventanas,
  la cortina y el estor, las vistas exteriores y la barandilla de la terraza.
- **Infografía con muebles:** sus detalles entran en los bocetos; en la composición se eliminan
  o modifican algunos con colores y materiales que combinen con los de la cocina, y con un
  retoque con máscara se añade una planta en maceta (ajuste del usuario: sin el perro).
- **Render final:** uno de día, otro al atardecer y otro de noche; queda seleccionado el de
  noche.
- Libertad creativa en el resto (notas, fichas, indicaciones, retoques, auditoría), recorriendo
  todas las opciones de la aplicación. Presupuesto: hasta 5,00 € (avisar al pasar de 3 €).

## Lo que aporta el usuario

- Paso 39: los costes reales de Azure de los últimos días (Cost Management).
