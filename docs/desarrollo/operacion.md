# Operación y herramientas

Comandos de línea de órdenes del backend. Con Docker, ejecútalos dentro del contenedor
(`docker compose exec backend …`); en desarrollo, desde `backend/` con `uv run`.

## Almacenamiento

```bash
python -m app.storage listar                                   # proyectos del índice
python -m app.storage ver <id>                                 # metadatos.json de un proyecto
python -m app.storage crear "Nombre" --descripcion "Salón"     # proyecto vacío
python -m app.storage reindexar                                # reconstruye proyectos.json
python -m app.storage papelera listar
python -m app.storage papelera restaurar <entrada>
python -m app.storage papelera vaciar [--dias N]               # DEFINITIVO: pide escribir VACIAR
```

Todos admiten `--data-dir DIR` para trabajar sobre otra carpeta de datos.

## Telemetría simulada

Genera llamadas simuladas (sin coste) con su telemetría, útil para probar la pestaña Costes IA:

```bash
python -m app.telemetry simular <id> --llamadas 6
```

Solo funciona en modo simulación. Los costes se consultan en la interfaz o con la API
(`GET /api/v1/projects/<id>/costs`).

## Comprobar la conexión con Azure

`app.foundry.smoke` hace una llamada real mínima por rol para verificar el `.env`, los
despliegues y los precios. **Tiene coste**: exige `AI_PROVIDER_MODE=azure` y pide confirmar cada
llamada (`s`).

```bash
docker compose exec backend python -m app.foundry.smoke --role FAST_DRAFT_MAKER
# sin --role, todos los roles; --out para la carpeta del informe
```

Deja un informe (`informe.json`) con la respuesta, los tokens, la latencia y el coste estimado
de cada llamada.

## Configuración

Para revisar la configuración cargada (la clave aparece enmascarada) y avisos como variables con
nombres antiguos:

```bash
uv run python -m shared
```

## Esquema de la API

```bash
cd backend && uv run python -m app.openapi   # docs/referencia/openapi.json
```
