# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones según
[SemVer](https://semver.org/lang/es/). El detalle de cada paso está en
[docs/pasos/](docs/pasos/README.md).

## [Sin publicar]

### Cambiado (incompatible: esquema v2 de los datos y de la API)

- Sin brief: cada generación escribe su propio prompt (PROMPT_ENGINEER) con sus entradas reales
  y guarda lo que ha entendido (`RenderRecord.prompt_info`); `/renders/drafts` ya no necesita un
  brief aprobado (Paso 22).

- Proyecto con nombre y descripción: sin tipo de espacio, notas de diseño, dimensiones, estilo
  ni presupuesto (su contenido pasa a la descripción); sin `/space-types` ni `crear --tipo`
  (Paso 17, B-026).
- Un solo tipo de imagen subida, `referencia` (sin capturas de SketchUp ni planos); la pestaña
  Assets queda con una sola lista (B-028).
- Renders sin estados «rechazado» ni «descartado» y sin `/reject` ni `/discard`; una sola imagen
  seleccionada por etapa (B-048, B-043).
- Retoques solo en composiciones, con la imagen completa del modelo: sin recomposición, sin
  retoque del render final, sin salida en bruto ni `/raw` (B-038).
- Migración automática de `metadatos.json` al esquema 2 al arrancar (y al restaurar de la
  papelera), con copia del original en `metadatos.v1.json`.
- El rol `CONTEXT_MANAGER` pasa a llamarse `REFERENCE_ANALYST` (`DEPLOYMENT_ROLE_REFERENCE_ANALYST`
  en `.env`); la telemetría anterior se lee con el nombre nuevo. Las fichas pasan a sol y los
  prompts a luna (Paso 18, B-052).
- Solo `STRUCTURAL_COMPOSER` admite máscara (B-037).

### Añadido

- Composición completa (Paso 23: B-038, B-039, B-045, B-046, B-055): auditoría opcional del
  boceto seleccionado frente a todas las referencias de perspectiva y geometría, con tus
  observaciones; retoque con máscara de la composición seleccionada (imagen completa del modelo,
  prompt escrito por la IA); y dos formas de generar, cada una con la miniatura de su imagen de
  partida: con el boceto seleccionado o con la composición actual, usando si quieres la
  auditoría y el retoque. Hasta 12 imágenes de apoyo, primero las del espacio; las que no caben
  se señalan en rojo.

- Estudio en tres pestañas (Bocetos, Composición y Render Final) que se desbloquean en orden.
  Bocetos parte de las referencias activas, con 1-8 variantes, calidad y formato. Cada imagen se
  ve en grande con «Ver más»: lo que entendió la IA, sus dudas, el prompt y lo enviado al modelo.
  La confirmación de coste aparece junto al botón, con un umbral de 0,15 € (Paso 22: B-035,
  B-036, B-042, B-043, B-047, B-049).

- Pestaña «Referencias» (antes Assets): cada imagen se sube de una en una con sus notas y se
  analiza al momento; su receta agrupa los ingredientes útiles (12 grupos, con «Otros») y la
  ficha de casillas guarda lo que el usuario quiere usar. Solo las referencias activas cuentan;
  descartar = desmarcar todo. API: `/assets/{id}/analyze` y `/assets/{id}/sheet` (sustituye a
  `/assets/{id}/analysis`). Paso 21: B-028 a B-030.

- Pestaña «Costes IA»: solo gasto real (también en el resumen del proyecto); gráficos con
  Altair y leyenda «rol (despliegue)» completa; registro con despliegue y MPx, detalle de la
  llamada al seleccionar una fila y CSV con todas las columnas; precios con las tarifas en
  columnas y sus unidades (Paso 20: B-031 a B-034).

- Proyectos: al abrir la app se activa el proyecto recordado o, si no hay, el último actualizado;
  el resumen desglosa el coste por rol y lista las llamadas de IA en un desplegable; la portada
  muestra la imagen más avanzada del proyecto; cabecera en el orden proyecto, backend y modo
  (Paso 19: B-025, B-027, B-044, B-050).

- Esfuerzo de razonamiento por rol de texto en `.env` (`PROMPT_ENGINEER_REASONING_EFFORT`,
  `REFERENCE_ANALYST_REASONING_EFFORT`; `medium` por defecto), junto al del auditor (B-053).
- Avisos de gasto real de IA: 3 € por proyecto y 10 € en total por defecto
  (`COST_ALERT_PROJECT_EUR`, `COST_ALERT_TOTAL_EUR`), en la cabecera, en Costes y al lanzar
  acciones con coste. Solo avisan (Paso 16, B-021).
- El coste acumulado de una imagen incluye la indexación de las fichas de referencias que usó
  el brief (B-022).

### Cambiado

- Bocetos, Composición y Render Final son pestañas de primer nivel (sin «Estudio»); la imagen
  seleccionada se ve en su proporción original; la ficha de una referencia muestra solo los
  nombres (el detalle, al pasar el ratón); umbral de confirmación de 0,20 € (Paso 23).

- Telemetría en `costes_telemetria.jsonl` (una línea por llamada, sin reescribir el archivo);
  el `costes_telemetria.json` anterior se migra solo y se conserva como `.json.migrado` (B-012).
- uv 0.13 en las imágenes Docker (Dependabot, #18) y 0.13.5 en la CI, alineadas (antes 0.12).

### Seguridad

- Pillow 13.0.0 (~40 alertas, varias críticas), certifi 2026.10.23 y brotli 1.2.1 (una crítica
  cada uno). Gradio 6.30 exige `pillow<13`: se fuerza con `override-dependencies` de uv hasta
  que lo admita (B-024). `uv.lock` pasa al formato de uv 0.13 (hace falta uv ≥ 0.13).

### Corregido

- Estimación de costes ajustada a la factura real de octubre de 2026: factor sobre los precios
  de lista (× 0,98463), megapíxel binario y 1 MP por imagen de referencia en FLUX. El modelo del
  brief mantiene su precio de lista aunque Azure lo cobró a 0 €.

## [1.0.0] — 2026-10-18

Primera versión completa: estudio de interiorismo asistido por IA con supervisión humana en
cada etapa.

### Añadido

- Estudio en tres pestañas (Bocetos, Composición y Render Final) que se desbloquean en orden.
  Bocetos parte de las referencias activas, con 1-8 variantes, calidad y formato. Cada imagen se
  ve en grande con «Ver más»: lo que entendió la IA, sus dudas, el prompt y lo enviado al modelo.
  La confirmación de coste aparece junto al botón, con un umbral de 0,15 € (Paso 22: B-035,
  B-036, B-042, B-043, B-047, B-049).

- Pestaña «Referencias» (antes Assets): cada imagen se sube de una en una con sus notas y se
  analiza al momento; su receta agrupa los ingredientes útiles (12 grupos, con «Otros») y la
  ficha de casillas guarda lo que el usuario quiere usar. Solo las referencias activas cuentan;
  descartar = desmarcar todo. API: `/assets/{id}/analyze` y `/assets/{id}/sheet` (sustituye a
  `/assets/{id}/analysis`). Paso 21: B-028 a B-030.

- Pestaña «Costes IA»: solo gasto real (también en el resumen del proyecto); gráficos con
  Altair y leyenda «rol (despliegue)» completa; registro con despliegue y MPx, detalle de la
  llamada al seleccionar una fila y CSV con todas las columnas; precios con las tarifas en
  columnas y sus unidades (Paso 20: B-031 a B-034).

- Proyectos: al abrir la app se activa el proyecto recordado o, si no hay, el último actualizado;
  el resumen desglosa el coste por rol y lista las llamadas de IA en un desplegable; la portada
  muestra la imagen más avanzada del proyecto; cabecera en el orden proyecto, backend y modo
  (Paso 19: B-025, B-027, B-044, B-050).

- Esfuerzo de razonamiento por rol de texto en `.env` (`PROMPT_ENGINEER_REASONING_EFFORT`,
  `REFERENCE_ANALYST_REASONING_EFFORT`; `medium` por defecto), junto al del auditor (B-053).

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
