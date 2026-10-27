# Configuración

Toda la configuración está en el archivo `.env` de la raíz del repositorio. Parte de la plantilla
`.env.example`, que trae comentada cada variable:

```bash
cp .env.example .env
```

!!! danger "El `.env` nunca se sube a git"
    Contiene tu clave de Azure. Está en `.gitignore` y el repositorio tiene controles que impiden
    subirlo; aun así, no lo compartas ni lo pegues en issues.

Tras cambiar el `.env`, reinicia el backend: `docker compose up -d backend`. Para comprobar la
configuración (con la clave enmascarada), desde un entorno de desarrollo: `uv run python -m
shared`.

## Modo de la IA

| Variable | Valores | Uso |
|----------|---------|-----|
| `AI_PROVIDER_MODE` | `mock` · `azure` | `mock`: simulación sin credenciales ni coste. `azure`: Azure AI Foundry, con coste |

## Azure AI Foundry

| Variable | Uso |
|----------|-----|
| `AZURE_FOUNDRY_ENDPOINT` | Solo el host del recurso, sin ruta: `https://<tu-recurso>.services.ai.azure.com` |
| `AZURE_FOUNDRY_API_KEY` | Clave del recurso |
| `AZURE_FOUNDRY_RENDERER_PATH` | Ruta del renderizador fotorrealista (API del proveedor) |
| `AZURE_FOUNDRY_RENDERER_ENDPOINT` | Opcional: host del renderizador si está en otro recurso |
| `AZURE_FOUNDRY_TIMEOUT_S` · `AZURE_FOUNDRY_MAX_RETRIES` | Tiempo máximo de espera y reintentos (solo ante cuota agotada o servicio no disponible; **un timeout nunca se reintenta**, porque Azure pudo cobrarlo) |

## Roles de IA y despliegues

El código nunca usa nombres de modelos: cada tarea es un **rol** y en el `.env` asocias cada rol
a un despliegue de tu recurso.

| Rol | Variable | Tarea | Tipo |
|-----|----------|-------|------|
| `REFERENCE_ANALYST` | `DEPLOYMENT_ROLE_REFERENCE_ANALYST` | Receta de cada referencia (una vez por imagen) | Texto con visión |
| `PROMPT_ARCHITECT` | `DEPLOYMENT_ROLE_PROMPT_ARCHITECT` | Prompt de cada generación, con lo que ha entendido y sus dudas | Texto con visión |
| `GEOMETRY_AUDITOR` | `DEPLOYMENT_ROLE_GEOMETRY_AUDITOR` | Auditoría del boceto frente a las referencias del espacio | Texto con visión y razonamiento |
| `FAST_DRAFT_MAKER` | `DEPLOYMENT_ROLE_FAST_DRAFT_MAKER` | Bocetos en lote | Edición de imagen |
| `COMPOSITION_BUILDER` | `DEPLOYMENT_ROLE_COMPOSITION_BUILDER` | Composición fiel y retoques con máscara | Edición de imagen con máscara |
| `REALISTIC_RENDERER` | `DEPLOYMENT_ROLE_REALISTIC_RENDERER` | Fotografía realista y cambios globales | Imagen fotorrealista |

### Razonamiento y tiempos de los roles de texto

| Variable | Por defecto | Uso |
|----------|-------------|-----|
| `PROMPT_ARCHITECT_REASONING_EFFORT` | `medium` | `low`, `medium` o `high`. Con `high` los prompts son más precisos y siguen costando céntimos |
| `PROMPT_ARCHITECT_TIMEOUT_S` | `300` | Con `high` puede razonar más de un minuto |
| `REFERENCE_ANALYST_REASONING_EFFORT` | `medium` | Esfuerzo del análisis de referencias |
| `GEOMETRY_AUDITOR_REASONING_EFFORT` | `medium` | Admite también `max` (más caro y lento) |
| `GEOMETRY_AUDITOR_TIMEOUT_S` | `900` | Las auditorías con razonamiento tardan minutos |

El razonamiento se factura como salida del modelo.

## Costes

### Tabla de precios

Los precios de cada despliegue están en `config/pricing.yaml`, en euros. Sirven para **estimar**
el coste de cada llamada; la cifra facturada es la de Azure Cost Management. Puedes editarla sin
reconstruir la imagen: se monta en solo lectura y basta con reiniciar el backend. Las claves son
los nombres de tus despliegues.

### Avisos de gasto

| Variable | Por defecto | Uso |
|----------|-------------|-----|
| `COST_ALERT_PROJECT_EUR` | `3` | Gasto real de un proyecto a partir del cual la interfaz avisa |
| `COST_ALERT_TOTAL_EUR` | `10` | Gasto real total a partir del cual avisa |

Solo avisan: nunca bloquean. Además, en modo Azure, cada acción de más de **0,20 €** pide un
segundo clic de confirmación junto al botón.

### Costes orientativos

Medidos en pruebas reales (precios de lista de octubre de 2026):

| Acción | Coste aproximado |
|--------|------------------|
| Receta de una referencia | 0,03-0,05 € |
| Prompt automático de una generación | 0,001-0,005 € |
| 4 bocetos en calidad media | 0,14-0,20 € |
| Composición o retoque | 0,05-0,06 € |
| Render final a 4 MP | 0,08 € |
| Auditoría del boceto | 0,14-0,25 € |

## Almacenamiento, red y contenedores

| Variable | Por defecto | Uso |
|----------|-------------|-----|
| `MAX_UPLOAD_MB` | `25` | Tamaño máximo de cada imagen subida |
| `BACKEND_PORT` · `FRONTEND_PORT` | `8000` · `7860` | Puertos publicados en `127.0.0.1` |
| `APP_UID` · `APP_GID` | `1000` | Usuario de los contenedores y propietario de `data/` (Linux) |
| `LOG_LEVEL` | `INFO` | Nivel del registro |

`DATA_DIR`, `PRICING_FILE`, `BACKEND_HOST` y `BACKEND_URL` son rutas y direcciones internas de
los contenedores: no hace falta cambiarlas con Docker.
