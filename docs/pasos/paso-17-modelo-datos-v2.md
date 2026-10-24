# Paso 17 — Modelo de datos v2 y migración

## 1. Objetivo

Primer paso del [plan de la versión 2.0.0](plan-version-2.md): cambiar el modelo de datos
(`metadatos.json` pasa al esquema 2) y la API para el flujo nuevo, con una migración automática
de los proyectos existentes. La interfaz solo se adapta lo justo para seguir funcionando; sus
cambios de fondo llegan en los Pasos 19 a 24. Sin llamadas reales a la IA.

## 2. Decisiones tomadas

| Tema | Decisión |
|------|----------|
| Descripción migrada (B-026) | La descripción anterior y, debajo, una línea por campo eliminado con valor: «Tipo de espacio: …», «Notas de diseño: …» (y dimensiones, estilo y presupuesto si los hubiera). Confirmado por el usuario |
| Selección migrada (B-043) | Una imagen seleccionada por etapa: si había varias, la decidida más tarde; si una etapa no tenía ninguna pero sí la siguiente, se selecciona la imagen de la que esta procede. Confirmado por el usuario |
| Tipo anterior de las imágenes (B-028) | Se conserva internamente (`Asset.legacy_kind`) como puente hasta el Paso 22. Confirmado por el usuario |
| Puente hasta el Paso 22 | La imagen base de bocetos, composiciones, brief y auditoría es la captura o el plano de la v1; en un proyecto sin ellos, la referencia en imagen más antigua (`app/pipelines/sources.py`). Las capturas y planos de la v1 no se indexan ni se usan como texturas del render final |
| Historia de la v1 | Se conservan los comentarios de rechazo, el intento al que sustituía cada imagen, los retoques de renders finales, sus guías y salidas en bruto, y las imágenes creadas con «Usar salida en bruto»; se siguen mostrando en el visor |
| API | Sigue siendo `/api/v1` con los cambios incompatibles documentados (decisión del plan): el frontend es su único cliente |

## 3. Implementación (un commit por entrada)

| Commit | Cambios |
|--------|---------|
| **B-026** Proyecto | `ProjectFields`: nombre y descripción (hasta 25 000 caracteres: cabe cualquier proyecto migrado). Sin `SpaceType`, `Dimensions`, `/space-types` ni `crear --tipo`. El brief recibe la descripción como contexto. `app/storage/migrations.py`: migración v1 → v2 al arrancar y al restaurar de la papelera, con copia previa en `metadatos.v1.json`; el índice v1 se reconstruye; la papelera lee el nombre de proyectos de cualquier esquema |
| **B-028** Imágenes | `AssetKind`: `referencia` y `render`. Solo se suben referencias (`/assets/referencia`). Migración: capturas y planos → referencias con `legacy_kind`; sus archivos se renombran a `referencias/` (si se corta, el siguiente arranque lo completa) y se quitan las carpetas vacías. Assets con una sola lista; portadas y resumen sin tipos |
| **B-048** Estados | `RenderStatus`: `generado` y `seleccionado`. Fuera `/reject` y `/discard` de los renders, la regeneración con comentarios y sus botones. Migración: descartados y rechazados → `generado` |
| **B-043** Selección | Seleccionar una imagen devuelve a `generado` la seleccionada antes en esa etapa. Migración según la decisión de arriba |
| **B-038** Retoques | Solo composiciones, con la máscara nativa del `STRUCTURAL_COMPOSER` y la imagen completa del modelo (sin recomponer). Fuera el retoque del render final, la guía, la salida en bruto, `/raw` y los archivos `bruto`/`guia` de `/inpaint/{archivo}`; se guarda solo la máscara |

Postman (46 peticiones), E2E y tests se actualizan en cada commit.

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 355 passed (migración: descripción, archivos, estados, selección, repetición tras un corte, papelera) |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Migración sobre una **copia** de `data/` | ✅ Ver la tabla siguiente; sin archivos perdidos y con `metadatos.v1.json` en los dos proyectos |
| Postman en local (mock, sobre la copia) | ✅ 46 peticiones, 82 comprobaciones |
| Playwright en local (mock, Edge) | ✅ 5/5 |
| CI de la PR #25 | ✅ lint y tests, gitleaks, Docker con newman y Playwright |

Ensayo de la migración sobre la copia de los datos reales:

| | Salón con Sofá Jattebo | Cocina con Electrodomésticos |
|---|---|---|
| Carpetas | 4 → `referencias`, `renders_historico` | 4 → `referencias`, `renders_historico` |
| Imágenes subidas | 1 captura + 2 referencias → 3 referencias (1 con `legacy_kind`) | 1 captura + 1 plano + 2 referencias → 4 referencias (2 con `legacy_kind`) |
| Renders | 19: 7 descartados o rechazados → generados | 12: 1 rechazado → generado |
| Seleccionados | final `d48a5331` y composición `5f1f30f7` → además el boceto `20115e2b` del que salió la composición | boceto `25606cc5` y composición `cffcf8e4` (sin final seleccionado, como antes) |
| Descripción | + «Tipo de espacio: Salón-cocina-comedor» y las notas de diseño | + «Tipo de espacio: Cocina» y las notas de diseño |

## 5. Estado final

⏳ En revisión — rama `feat/paso-17`, PR #25 pendiente de validación por el usuario. Los datos
locales se migrarán solos al reconstruir Docker tras el merge (los originales quedan como
`metadatos.v1.json`).

## 6. Pendiente / futuro

- B-026, B-028, B-038 y B-043 siguen abiertas en su parte de interfaz (Pasos 19 a 23).
- `legacy_kind` y `app/pipelines/sources.py` desaparecen en el Paso 22, cuando se elija la
  imagen de partida.
