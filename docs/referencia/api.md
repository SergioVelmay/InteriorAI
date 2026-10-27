# API REST

El backend expone una API REST en `/api/v1` (y `GET /health` sin prefijo). Es la que usa la
interfaz y la que puedes usar para integrar InteriorAI o automatizar tareas.

!!! tip "Probarla en tu equipo"
    Con la aplicación en marcha, el Swagger interactivo («Try it out») está en
    <http://127.0.0.1:8000/docs>. El de esta página es solo de consulta: la web no tiene un
    backend al que llamar.

## Convenciones

| Tema | Convención |
|------|------------|
| Rutas y campos | En inglés (`/projects/{project_id}/renders/drafts`); los valores de los enumerados y los textos, en español (`"boceto"`, `"seleccionado"`) |
| Identificadores | UUID en todas las rutas (protege de rutas maliciosas) |
| Errores | Siempre `{"detail": "<mensaje en español>"}`, con el código de estado de la tabla de abajo |
| `X-Request-ID` | Cada respuesta lo lleva (si envías uno válido, se respeta). Enlaza la petición con sus llamadas a la IA en la telemetría |
| Coste | Las respuestas de los endpoints que llaman a la IA incluyen `cost_eur` (coste estimado de esa petición) y `request_id` |
| Subidas | Multipart (`file`) o Base64 (`/base64`). El tipo se detecta por el contenido (PNG, JPEG o WebP), con límite de tamaño (`MAX_UPLOAD_MB`) y de 80 MP. Un archivo repetido en el proyecto devuelve 409 (salvo `?allow_duplicate=true`) |
| Borrado | Suave: proyectos e imágenes pasan a la papelera |

### Códigos de error

| Código | Cuándo |
|--------|--------|
| 400 | Operación no admitida por el rol de IA (p. ej. máscara en el renderizador) |
| 404 | Proyecto, imagen o render inexistente |
| 409 | Transición no permitida (p. ej. generar la composición con un boceto no seleccionado) o archivo duplicado |
| 413 | Petición o imagen demasiado grande |
| 415 | Archivo que no es una imagen admitida o está dañado |
| 422 | Validación de la petición o entrada no válida para la etapa; contenido bloqueado por el filtro de Azure |
| 429 | Cuota de Azure agotada (tras reintentar) |
| 500 | Datos dañados en `data/` (el detalle, solo en el registro) |
| 502 | Error de Azure o respuesta de la IA que no cumple el esquema |
| 504 | Timeout de la IA (nunca se reintenta) |

## Endpoints por grupos

=== "Proyectos y assets"

    | Método | Ruta | Uso |
    |--------|------|-----|
    | `GET` | `/health` | Estado: versión, modo de la IA y si `data/` es escribible (503 si no) |
    | `GET` · `POST` | `/api/v1/projects` | Listar (más reciente primero) · crear |
    | `GET` · `PATCH` · `DELETE` | `/api/v1/projects/{project_id}` | Consultar · editar nombre y descripción · mover a la papelera |
    | `POST` | `/api/v1/projects/{project_id}/assets/{kind}` | Subir una referencia (`kind=referencia`) |
    | `POST` | `/api/v1/projects/{project_id}/assets/{kind}/base64` | Subir en Base64 |
    | `GET` | `/api/v1/projects/{project_id}/assets` | Listar (`?kind=`) |
    | `GET` · `PATCH` · `DELETE` | `/api/v1/projects/{project_id}/assets/{asset_id}` | Consultar · editar sus notas · mover a la papelera |
    | `GET` | `/api/v1/projects/{project_id}/assets/{asset_id}/content` | Descargar la imagen |
    | `GET` | `/api/v1/asset-kinds` | Tipos de imagen admitidos |

=== "Referencias"

    | Método | Ruta | Uso |
    |--------|------|-----|
    | `POST` | `/api/v1/projects/{project_id}/assets/{asset_id}/analyze` | Receta de una referencia con sus notas (al subirla o de nuevo con otras notas) |
    | `POST` | `/api/v1/projects/{project_id}/references/index` | Analizar en bloque las referencias sin receta (`force` para todas) |
    | `PUT` | `/api/v1/projects/{project_id}/assets/{asset_id}/sheet` | Guardar la ficha: los elementos marcados (`"grupo:índice"`); vacía = descartada |

=== "Renders"

    | Método | Ruta | Uso |
    |--------|------|-----|
    | `POST` | `/api/v1/projects/{project_id}/renders/drafts` | Bocetos (1-8 variantes) a partir de las referencias activas |
    | `POST` | `/api/v1/projects/{project_id}/renders/compositions` | Composición desde el boceto seleccionado o la composición actual (`source`), opcionalmente con la auditoría (`use_audit`) |
    | `POST` | `/api/v1/projects/{project_id}/renders/final` | Render final desde la composición seleccionada o el render final actual; `variant_of` repite uno («Otra versión») |
    | `GET` | `/api/v1/projects/{project_id}/renders` | Historial (`?stage=boceto\|composicion\|render_final`) |
    | `POST` | `/api/v1/projects/{project_id}/renders/{render_id}/select` | Seleccionar (la anterior de la etapa deja de estarlo) |
    | `POST` | `/api/v1/projects/{project_id}/renders/{render_id}/audit` | Auditar frente a las referencias del espacio, con observaciones |
    | `POST` | `/api/v1/projects/{project_id}/renders/{render_id}/inpaint` | Retocar una zona de una composición (máscara + instrucción) |
    | `GET` | `/api/v1/projects/{project_id}/renders/{render_id}/inpaint/{file}` | Máscara de un retoque |

=== "Costes"

    | Método | Ruta | Uso |
    |--------|------|-----|
    | `GET` | `/api/v1/projects/{project_id}/costs` | Gasto del proyecto: totales y desgloses por rol, día y despliegue, y últimas llamadas |
    | `GET` | `/api/v1/costs` | Lo mismo para todos los proyectos |
    | `GET` | `/api/v1/costs/alerts` | Gasto real frente a los umbrales de aviso |
    | `GET` | `/api/v1/projects/{project_id}/renders/{render_id}/cost` | Coste acumulado de la cadena que lleva a una imagen |
    | `GET` | `/api/v1/pricing` | Tabla de precios vigente |

## Ejemplo: de un proyecto a los bocetos

```bash
API=http://127.0.0.1:8000/api/v1

# 1. Crear el proyecto
curl -s -X POST $API/projects -H "Content-Type: application/json" \
  -d '{"name": "Salón", "description": "Salón luminoso de estilo nórdico"}'

# 2. Subir una referencia y analizarla (con coste en modo azure)
curl -s -X POST $API/projects/<id>/assets/referencia -F "file=@vista.png"
curl -s -X POST $API/projects/<id>/assets/<asset_id>/analyze \
  -H "Content-Type: application/json" -d '{"notes": "Quédate con el punto de vista"}'

# 3. Generar 4 bocetos en calidad media
curl -s -X POST $API/projects/<id>/renders/drafts \
  -H "Content-Type: application/json" -d '{"n": 4, "quality": "medium"}'
```

!!! warning "En Windows"
    En Git Bash, `curl -d` con tildes puede enviar el texto mal codificado: usa el Swagger, Postman
    o un script.

La colección de Postman del repositorio
([`postman/`](https://github.com/SergioVelmay/InteriorAI/tree/main/postman)) recorre el flujo
completo de la API.

## Swagger

Esquema OpenAPI completo, con todos los modelos de petición y respuesta
([descargar `openapi.json`](openapi.json)).

<swagger-ui src="openapi.json"/>
