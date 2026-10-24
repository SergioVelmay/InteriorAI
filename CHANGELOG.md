# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones según
[SemVer](https://semver.org/lang/es/). El detalle de cada paso está en
[docs/pasos/](docs/pasos/README.md).

## [Sin publicar]

### Añadido

- Avisos de gasto real de IA: 3 € por proyecto y 10 € en total por defecto
  (`COST_ALERT_PROJECT_EUR`, `COST_ALERT_TOTAL_EUR`), en la cabecera, en Costes y al lanzar
  acciones con coste. Solo avisan (Paso 16, B-021).
- El coste acumulado de una imagen incluye la indexación de las fichas de referencias que usó
  el brief (B-022).

### Cambiado

- Telemetría en `costes_telemetria.jsonl` (una línea por llamada, sin reescribir el archivo);
  el `costes_telemetria.json` anterior se migra solo y se conserva como `.json.migrado` (B-012).

### Seguridad

- Pillow 13.0.0 (~40 alertas, varias críticas), certifi 2026.10.23 y brotli 1.2.1 (una crítica
  cada uno). Gradio 6.30 exige `pillow<13`: se fuerza con `override-dependencies` de uv hasta
  que lo admita (B-024). `uv.lock` pasa al formato de uv 0.13 (hace falta uv ≥ 0.13).

### Corregido

- Estimación de costes ajustada a la factura real de octubre de 2026: factor sobre los precios
  de lista (× 0,98463), megapíxel binario y 1 MP por imagen de referencia en FLUX. El modelo del
  brief mantiene su precio de lista aunque Azure lo cobró a 0 €.

### Cambiado

- uv 0.13 en las imágenes Docker (Dependabot, #18) y 0.13.5 en la CI, alineadas (antes 0.12).
  Sin cambios en `uv.lock` ni en el comportamiento: Python sigue fijado a 3.11.

## [1.0.0] — 2026-10-18

Primera versión completa: estudio de interiorismo asistido por IA con supervisión humana en
cada etapa.

### Añadido

- **Configuración y seguridad** (Pasos 0-3): repositorio público con secretos solo en `.env`
  (`SecretStr`), gitleaks y bloqueos en pre-commit; Docker Compose con puertos solo en
  `127.0.0.1`, usuario sin privilegios y frontend sin credenciales.
- **Almacenamiento y API** (Pasos 4-5): proyectos en `data/` con escritura atómica y bloqueo
  por proyecto, borrado suave a la papelera; API REST v1 (proyectos, assets con validación por
  contenido) y colección de Postman.
- **Azure AI Foundry por roles** (Paso 6): seis roles funcionales, cliente único con modo mock,
  reintentos solo en 429/503 (nunca en un timeout).
- **Telemetría de costes** (Paso 7): coste estimado por llamada con `config/pricing.yaml`.
- **Pipelines** (Pasos 8-10): fichas de referencias, brief de diseño, bocetos, composición y
  render final; auditoría geométrica a demanda; selección, descarte y rechazo con comentarios.
- **Interfaz Gradio** (Pasos 11-14): Proyectos, Assets, Estudio (ciclo HITL completo con
  confirmación de las acciones con coste en Azure) y Costes (por rol, día y proyecto; coste
  acumulado de cada imagen).
- **Retoques de zona** (Paso 13b): pincel sobre composición o render final con recomposición
  local exacta; salida en bruto del modelo disponible como imagen; render final con la
  proporción exacta de la captura (16:9 → 1920×1080).
- **CI y seguridad del repositorio** (Paso 15a): GitHub Actions (lint, tests, gitleaks sobre
  todo el historial, imágenes Docker, Postman y Playwright), Dependabot, escaneo de secretos con
  bloqueo en el push, protección de `main` y `SECURITY.md`.
- **Operación** (Paso 15b): contenedores endurecidos (solo lectura, sin capacidades, sin
  escalada de privilegios, límites de recursos), usuario configurable (`APP_UID`/`APP_GID`) y
  comando de papelera (`listar`, `restaurar`, `vaciar` con confirmación).

[1.0.0]: https://github.com/SergioVelmay/InteriorAI/releases/tag/v1.0.0
