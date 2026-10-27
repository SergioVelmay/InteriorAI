# Instalación

## Con Docker (recomendado)

```bash
git clone https://github.com/SergioVelmay/InteriorAI.git
cd InteriorAI
cp .env.example .env      # funciona tal cual en modo simulación (sin coste ni credenciales)
mkdir -p data             # tus proyectos; nunca se sube a git
docker compose up --build -d
```

Cuando termine, comprueba que los contenedores están sanos:

```bash
docker compose ps         # data-init «Exited (0)»; backend y frontend «healthy»
```

| Servicio | Dirección |
|----------|-----------|
| Interfaz | <http://127.0.0.1:7860> |
| API (Swagger) | <http://127.0.0.1:8000/docs> |
| Estado del backend | <http://127.0.0.1:8000/health> |

!!! info "Solo en tu equipo"
    Los puertos se publican únicamente en `127.0.0.1`: la aplicación no es accesible desde otros
    equipos de la red.

### En Linux

Los contenedores se ejecutan con el usuario 1000. Si el tuyo es otro, ajústalo en `.env` para que
pueda escribir en `data/`:

```dotenv
APP_UID=1001   # id -u
APP_GID=1001   # id -g
```

## Pasar al modo Azure

1. Rellena en `.env` el endpoint, la clave y los despliegues de cada rol
   ([Configuración](configuracion.md)).
2. Pon `AI_PROVIDER_MODE=azure`.
3. Reinicia el backend:

    ```bash
    docker compose up -d backend
    ```

La cabecera de la interfaz pasará a mostrar «Azure · con coste».

## Actualizar a una versión nueva

```bash
git pull
docker compose up --build -d
```

Los datos se migran solos al arrancar cuando cambia su esquema; antes de migrar, cada proyecto
guarda una copia de su `metadatos.json`. Revisa las notas de cada versión en
[Versiones](../proyecto/versiones.md), sobre todo si cambian variables del `.env`.

## Comandos útiles

```bash
docker compose logs -f backend          # registro del backend
docker compose down                     # parar (los datos se conservan)
docker compose exec backend python -m app.storage listar
docker compose exec backend python -m app.storage papelera listar
docker compose exec backend python -m app.storage papelera restaurar <entrada>
docker compose exec backend python -m app.storage papelera vaciar --dias 30   # pide escribir VACIAR
```

!!! warning "Vaciar la papelera es definitivo"
    Borrar un proyecto desde la interfaz solo lo mueve a `data/.papelera/` (se puede restaurar).
    Vaciar la papelera lo elimina para siempre.

## Problemas frecuentes

| Síntoma | Qué hacer |
|---------|-----------|
| El backend no arranca en modo Azure | Revisa `docker compose logs backend`: si falta alguna variable obligatoria, el mensaje dice cuál |
| Aviso de variables con nombres antiguos | Desde la 3.0.0 los roles tienen nombres nuevos: renómbralas según [Versiones](../proyecto/versiones.md) |
| `Permission denied` en `data/` (Linux) | Ajusta `APP_UID` y `APP_GID` a tu usuario |
| El puerto 7860 u 8000 está ocupado | Cambia `FRONTEND_PORT` o `BACKEND_PORT` en `.env`, o libera el puerto |
