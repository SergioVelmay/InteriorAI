# Plan de acción — InteriorAI 2.1.0

Propuesto el 2026-10-25, tras la ronda de observaciones del usuario sobre la 2.0.0: un flujo
completo guiado («Personalización Cocina Los Molinos»), de la creación del proyecto a los renders
finales, con capturas de trabajo en cada etapa. Recoge las 25 observaciones (O-1 a O-25) como
entradas **B-057 a B-081** del [backlog](BACKLOG.md) (O-n → B-(056 + n)) y cierra con las
capturas del README (B-023).

## Por qué 2.1.0

Son mejoras de interfaz y de prompts sin cambios en el esquema de datos ni en la API. La única
excepción es el renombrado de roles (B-057), que cambia variables del `.env`: ver la decisión 1.

## Criterio de orden

1. Nombres y costes primero: el renombrado toca muchos archivos y conviene hacerlo antes de
   rehacer pantallas.
2. Estilo común (pestañas, escala de imágenes, letra, textos de Gradio) y las pestañas que lo
   estrenan: Proyectos y Referencias.
3. Bocetos: maquetación y prompts, con llamadas reales.
4. Composición y Render Final: editor y detalles.
5. Capturas y publicación.

Cada paso, como siempre: explicación y OK del usuario, rama `feat/paso-NN`, tests + Postman + E2E
actualizados y CI en verde, PR revisada y mergeada por el usuario.

## Pasos

| Paso | Contenido | Entradas | Llamadas reales |
|------|-----------|----------|-----------------|
| 26. Roles y Costes IA | Renombrado de los cinco roles (código, `.env`, prompts, docs, Postman), lectura de los datos antiguos con los nombres nuevos; costes agrupados por el rol actual de cada despliegue (6 series); colores vivos y contrastados; leyenda única y gráficos apilados (día y proyecto) | B-057, B-080, B-081 | Opcional: una llamada de texto por rol renombrado para comprobar el `.env` (≈ 0,01 €) |
| 27. Estilo común, Proyectos y Referencias | Pestaña activa en blanco y negrita; escala única de imágenes (1/1, 1/2, 1/4, 1/6); letra pequeña común; textos de Gradio en español; previsión de tiempo sin historial; 50/50 real; resumen del proyecto; recarga de Proyectos al entrar; vista previa de la referencia en su proporción; pie de las miniaturas en dos líneas | B-058 a B-066, B-079 | No |
| 28. Bocetos | Maquetación a ancho completo; prompts sin elementos no marcados, sin dibujar anotaciones y con bocetos realistas y minimalistas (también en composición y render final) | B-067 a B-070 | ≈ 0,40-0,60 € (varias tandas de bocetos y alguna composición) |
| 29. Composición y Render Final | Iconos del editor; rueda del ratón sobre el lienzo; aviso de retoque e indicaciones; secciones plegables; tabla de la auditoría; texto del coste de la cadena; prompt con ajuste de línea; Render Final sin «calidad» | B-071 a B-078 | No |
| 30. Capturas y versión 2.1.0 | Caso de demostración del usuario sin marcas; capturas del README con Playwright, solo mirando (sin acciones de IA ni cambios de selección); README, CHANGELOG, etiqueta y Release | B-023 | No |

## Decisiones pendientes (para el Paso 26)

1. **Variables del `.env` con los nombres antiguos.** Renombrarlas rompe cualquier `.env` de la
   2.0.0. Opciones: **(a)** aceptar también los nombres antiguos durante la 2.x, con un aviso
   en el registro (sigue siendo versión menor: 2.1.0); **(b)** solo los nombres nuevos y
   publicar como 3.0.0. Recomendado: (a).

## Lo que aporta el usuario

- Paso 26: la decisión 1.
- Paso 28: revisar juntos los prompts de bocetos y composición tras las pruebas reales.
- Paso 30: el proyecto de demostración terminado, sin marcas, con la aplicación levantada.
