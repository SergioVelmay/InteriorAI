# Primeros pasos

InteriorAI se ejecuta en tu equipo con **Docker**: un contenedor con la API (backend) y otro con
la interfaz web (frontend). Tus proyectos se guardan en la carpeta `data/` del repositorio.

## Dos modos de funcionamiento

=== "Simulación (mock)"

    Es el modo por defecto. **No necesita credenciales ni tiene coste**: las imágenes y los textos
    de la IA son simulados (marcos de colores con el texto «MOCK»). Sirve para conocer la
    aplicación, probar el flujo y desarrollar.

    ```dotenv
    AI_PROVIDER_MODE=mock
    ```

=== "Azure AI Foundry"

    La IA de verdad, con **coste por uso** en tu suscripción de Azure. Necesitas un recurso de
    Azure AI Foundry con un despliegue por cada rol (ver [Configuración](configuracion.md)).

    ```dotenv
    AI_PROVIDER_MODE=azure
    ```

    La interfaz lo indica siempre en la cabecera («Azure · con coste») y cada botón con coste
    muestra una estimación antes de pulsarlo.

## Qué necesitas

| Para | Necesitas |
|------|-----------|
| Usar la aplicación | [Docker Desktop](https://www.docker.com/products/docker-desktop/) (o Docker Engine con Compose v2) y Git |
| Generar con IA real | Una suscripción de Azure con un recurso de **Azure AI Foundry** y los despliegues de cada rol |
| Desarrollar | [uv](https://docs.astral.sh/uv/) (instala Python 3.11) |

## Siguiente paso

1. [Instala InteriorAI](instalacion.md) y ábrelo en `http://127.0.0.1:7860`.
2. Si vas a usar Azure, [configura tu `.env`](configuracion.md).
3. Sigue el [manual de usuario](../manual/index.md) con un caso completo.
