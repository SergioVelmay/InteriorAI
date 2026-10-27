# IA y costes

## Roles en lugar de modelos

El código nunca usa nombres de modelos: cada tarea es un **rol** y el `.env` asocia cada rol a un
despliegue de Azure AI Foundry (`DEPLOYMENT_ROLE_*`). Cambiar de modelo es cambiar el `.env` (y
su precio en `config/pricing.yaml`), sin tocar código.

| Rol | Tipo de API | Tarea |
|-----|-------------|-------|
| `REFERENCE_ANALYST` | Responses (texto con visión) | Receta de cada referencia, en 12 grupos, con medidas y su origen |
| `PROMPT_ARCHITECT` | Responses | Prompt de cada generación con sus entradas reales; explica lo que ha entendido |
| `GEOMETRY_AUDITOR` | Responses con razonamiento | Auditoría del boceto frente a las referencias del espacio |
| `FAST_DRAFT_MAKER` | Images (edición) | Bocetos en lote |
| `COMPOSITION_BUILDER` | Images (edición con máscara) | Composición y retoques; el **único** rol con máscara |
| `REALISTIC_RENDERER` | API del proveedor | Fotografía realista: recibe solo la imagen de partida y el prompt |

| Superficie | Ruta |
|------------|------|
| Responses | `{endpoint}/openai/v1/responses` (salida estructurada con esquema JSON estricto) |
| Images | `{endpoint}/openai/v1/images/edits` |
| Proveedor del renderizador | `{endpoint}{AZURE_FOUNDRY_RENDERER_PATH}?api-version=preview` (una imagen por petición, hasta 4 MP, sin máscara) |

## El cliente de IA

Toda llamada pasa por un `FoundryClient`
([`backend/app/foundry/`](https://github.com/SergioVelmay/InteriorAI/tree/main/backend/app/foundry)):

- **`AzureFoundryClient`** en modo `azure`, **`MockFoundryClient`** en modo `mock` (textos e
  imágenes simulados, tokens aproximados, sin red).
- Envuelto siempre en un cliente con **telemetría** que mide latencia, tokens (entrada, caché,
  salida, razonamiento), imágenes y megapíxeles, estima el coste y lo guarda en el proyecto. Las
  llamadas fallidas también se registran.
- Valida que cada rol solo haga lo que puede (p. ej. máscara solo en `COMPOSITION_BUILDER`).

### Reintentos y tiempos

| Situación | Comportamiento |
|-----------|----------------|
| 429 (cuota) o 503 (no disponible) | Se reintenta, respetando `Retry-After`, hasta `AZURE_FOUNDRY_MAX_RETRIES` |
| **Timeout** | **Nunca se reintenta**: Azure pudo completar y cobrar el trabajo aunque la respuesta no llegara |
| Respuesta incompleta (tope de salida) | Error 502; se registra lo facturado |
| Contenido bloqueado por el filtro | Error 422 |

Timeouts: `AZURE_FOUNDRY_TIMEOUT_S` (120 s) en general, `PROMPT_ARCHITECT_TIMEOUT_S` (300 s) y
`GEOMETRY_AUDITOR_TIMEOUT_S` (900 s). El razonamiento de los roles de texto se configura por rol
(`<ROL>_REASONING_EFFORT`) y se factura como salida.

## Prompts

### Prompts de sistema

Viven en
[`backend/app/pipelines/prompts/`](https://github.com/SergioVelmay/InteriorAI/tree/main/backend/app/pipelines/prompts),
en Markdown, y se editan sin tocar código. Cada imagen guarda la **versión** (hash del contenido)
del prompt que la generó.

| Archivo | Rol | Uso |
|---------|-----|-----|
| `reference_analyst.md` | `REFERENCE_ANALYST` | La receta de una referencia |
| `prompt_bocetos.md` | `PROMPT_ARCHITECT` | Prompt de los bocetos |
| `prompt_composicion.md` | `PROMPT_ARCHITECT` | Prompt de la composición y de los retoques |
| `prompt_render_final.md` | `PROMPT_ARCHITECT` | Prompt del render final |
| `prompt_criterios.md` | `PROMPT_ARCHITECT` | Criterios comunes: medidas (estándar de mercado si faltan), dudas resueltas como interiorista, distribución de izquierda a derecha, repaso final |
| `auditor_espacio.md` | `GEOMETRY_AUDITOR` | La auditoría frente a las referencias del espacio |

### Prompt automático de cada generación

En cada generación, el `PROMPT_ARCHITECT` recibe:

- la descripción del proyecto;
- las imágenes que recibirá el modelo de imagen, numeradas y con su papel (imagen base, imagen de
  partida, apoyo);
- de cada referencia activa, el resumen de su análisis, tus notas, **lo marcado** y, de las que
  se envían como imagen, **lo no marcado** (para decir al modelo qué no tomar);
- el historial de la imagen de partida (lo entendido en cada etapa y los retoques pedidos) y las
  generaciones anteriores de la etapa, con sus dudas;
- tus indicaciones, el formato de salida y, si aplica, las correcciones de la auditoría o la zona
  del retoque.

Devuelve el prompt (en inglés), lo que ha entendido y sus dudas (en español), que la interfaz
muestra con cada imagen.

## Cálculo del coste

Cada llamada se estima con los precios de `config/pricing.yaml` (en euros):

| Tipo de precio | Se cobra por | Ejemplo de rol |
|----------------|--------------|----------------|
| `tokens` | Millón de tokens: entrada, entrada en caché, escritura en caché y salida (con precio *long* si la entrada supera el umbral) | Roles de texto |
| `image_tokens` | Millón de tokens: texto de entrada, imagen de entrada y salida | Bocetos y composición |
| `megapixels` | Primer megapíxel, megapíxeles adicionales y megapíxeles de las imágenes de referencia | Render final |

El resultado se multiplica por `billing_factor` (ajuste al tipo de cambio de la factura) y se
guarda en la telemetría. Es una **estimación**: la cifra facturada es la de Azure Cost
Management.

### Coste de la cadena

Cada imagen muestra lo que ha costado llegar a ella: suma, por `request_id`, los lotes completos
de su cadena (con su prompt automático), los retoques, las auditorías y las recetas de las
referencias enviadas como imagen. Las ramas descartadas no cuentan; las llamadas simuladas van
aparte.

### Avisos y confirmaciones

- En modo Azure, cada acción de más de 0,20 € pide un segundo clic de confirmación.
- La cabecera avisa cuando el gasto real de un proyecto o el total supera
  `COST_ALERT_PROJECT_EUR` o `COST_ALERT_TOTAL_EUR`.
