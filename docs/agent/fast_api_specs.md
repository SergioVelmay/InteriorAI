# FastAPI — especificaciones y convenciones

> Estado: **diseño** (Paso 1). Se completa en los Pasos 3, 4, 5 y 7.

## Convenciones

- Prefijo de versión: `/api/v1`. Healthcheck sin prefijo: `GET /health`.
- Async en todos los endpoints; I/O de disco con `anyio`/`aiofiles` o en threadpool.
- Errores con `HTTPException` y cuerpo `{"detail": ...}`; `404` recurso inexistente,
  `409` transición HITL no permitida, `413` payload demasiado grande, `422` validación.
- Cada petición recibe un `X-Request-ID` (middleware) que se propaga a la telemetría.
- El backend es el **único escritor** de `data/`.

## Almacenamiento (Paso 4)

```
data/
├── proyectos.json                    # índice global
└── {id_proyecto}/                    # id = UUID (protección path traversal)
    ├── metadatos.json
    ├── costes_telemetria.json
    ├── planos/
    ├── referencias/
    ├── capturas_sketchup/
    └── renders_historico/            # cada render: imagen + JSON sidecar
```

Escritura atómica (temp + `os.replace`) bajo lock por proyecto (decisión D4).

## Endpoints previstos

| Método | Ruta | Paso |
|--------|------|------|
| GET | `/health` | 3 |
| POST/GET | `/api/v1/proyectos` | 5 |
| GET/PATCH/DELETE | `/api/v1/proyectos/{id}` | 5 |
| POST/GET | `/api/v1/proyectos/{id}/assets/{tipo}` | 5 |
| GET | `/api/v1/proyectos/{id}/costes` | 7 |
| POST | `/api/v1/proyectos/{id}/pipelines/...` | 8–9 |
| POST | `/api/v1/proyectos/{id}/iteraciones/{it}/{aprobar\|rechazar}` | 10 |

Uploads: multipart y Base64, límite `MAX_UPLOAD_MB`, validación de MIME.
