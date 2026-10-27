# Interfaz

La interfaz es una aplicación de [Gradio](https://www.gradio.app/) 6
([`frontend/ui/`](https://github.com/SergioVelmay/InteriorAI/tree/main/frontend/ui)), en
español y con tema oscuro. **No tiene credenciales**: escribe siempre a través de la API y lee
las imágenes directamente del volumen `data/`, montado en solo lectura.

## Pestañas

| Pestaña | Módulo | Qué hace |
|---------|--------|----------|
| Proyectos | `tabs/projects.py` | Galería con portadas, crear, editar, resumen del proyecto, llamadas de IA y papelera |
| Referencias | `tabs/references.py` | Subir con notas, análisis inmediato, ficha de casillas por grupo, guardar, volver a analizar |
| Bocetos · Composición · Render Final | `tabs/studio.py` | Las tres etapas del estudio, que se desbloquean en orden: cada una exige una imagen seleccionada en la anterior |
| Costes IA | `tabs/costs.py` | Indicadores, gráficos por rol, día y proyecto, registro de llamadas (el detalle de una fila se oculta al hacer clic fuera), CSV y precios |

La lógica de presentación (textos, miniaturas, tablas) está separada en módulos de vistas
(`views.py`, `studio_views.py`, `cost_views.py`) que se prueban sin abrir la interfaz.

## Comportamiento común

- **Proyecto activo:** se recuerda en el navegador (`gr.BrowserState`); por defecto, el último
  actualizado. La cabecera muestra el proyecto, el estado del backend y el modo de la IA
  («Simulación · sin coste» o «Azure · con coste»).
- **Portada de cada proyecto:** la imagen más avanzada que exista (render final seleccionado,
  composición, boceto o la primera referencia).
- **Estimación y confirmación:** cada botón con coste muestra una estimación, que se recalcula
  al cambiar las variantes, la calidad o la resolución; en modo Azure, por encima de 0,20 € pide
  confirmarlo en un cuadro rojo, que se oculta al pulsar para no confirmar
  dos veces.
- **Previsión de tiempo:** mientras trabaja la IA se ve «procesando | transcurrido/previsto».
  Gradio solo conoce la media de las ejecuciones anteriores; InteriorAI siembra la previsión
  medida en pruebas reales para que se vea desde la primera vez (`forecast.py`).
- **Trazabilidad de cada imagen:** lo que ha entendido la IA, sus dudas, las entradas, el prompt
  enviado, las imágenes enviadas al modelo y el coste acumulado de la cadena.

## Editor de máscara

El retoque de una composición usa el `ImageEditor` de Gradio con ajustes propios:

- Pincel rojo fijo (sin paleta), goma y tamaño; la herramienta activa se resalta en blanco.
- La rueda del ratón sobre el lienzo desplaza la página (el zoom queda en sus botones).
- El valor del editor solo se envía al generar (un botón puente oculto), y se crea un editor
  nuevo por cada composición seleccionada.

## Tema y textos

- Tema oscuro forzado (zinc/slate) definido en `theme.py`, con CSS propio para miniaturas,
  galerías, tablas y el editor.
- Los textos internos de Gradio se fuerzan al español sea cual sea el idioma del navegador
  (`launch(i18n=...)`).
- Escala única de imágenes: vistas a ancho completo, galerías de 2 o 4 por fila y miniaturas de
  1/4 o 1/6 del ancho.
