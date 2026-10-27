# Referencia técnica

Cómo está hecho InteriorAI por dentro, para quien quiera integrarlo, auditarlo o entender sus
decisiones.

<div class="grid cards" markdown>

-   :material-sitemap: **[Arquitectura](arquitectura.md)**

    ---

    Contenedores, flujo de una generación y principios de diseño.

-   :material-api: **[API REST](api.md)**

    ---

    Convenciones, endpoints por grupos y el Swagger completo.

-   :material-database: **[Datos y almacenamiento](datos.md)**

    ---

    Modelo de datos, carpeta `data/`, escritura atómica, papelera y migraciones.

-   :material-robot: **[IA y costes](ia-y-costes.md)**

    ---

    Roles, Azure AI Foundry, prompts automáticos, telemetría y cálculo del coste.

-   :material-monitor-dashboard: **[Interfaz](interfaz.md)**

    ---

    La aplicación de Gradio: pestañas, tema, editor de máscara y previsiones.

</div>

Para contribuir al código, ver [Desarrollo](../desarrollo/index.md).

## En una frase

Un **backend FastAPI** es el único que escribe en `data/` y el único que llama a la IA (por
roles, nunca por nombre de modelo, y siempre midiendo el coste); una **interfaz Gradio** sin
credenciales lee las imágenes del volumen y escribe a través de la API; cada etapa del diseño
parte de la imagen que **el usuario** eligió en la anterior.
