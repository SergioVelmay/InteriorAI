# Paso 52 — Pruebas E2E, capturas del manual y protección de datos

## 1. Objetivo

Cerrar cuatro pendientes de calidad y seguridad:

- **B-121.** Cubrir en Playwright el comportamiento de las dos casillas de superposición geométrica
  añadido en el Paso 51.
- Actualizar las capturas de Proyectos, Bocetos, Composición y Render Final para reflejar la interfaz
  actual, incluidos los cuadros de indicaciones, los descartes y las comparativas del esquema 3D.
- Impedir que imágenes sueltas de una vivienda puedan añadirse desde la raíz del repositorio público,
  aunque midan menos de 1 MB.
- Corregir la coma de B-116 y cerrar la documentación del Paso 51, ya mergeado.

Todo se realiza en modo `mock`, con un proyecto sintético sin dirección ni datos reales. Coste: 0 €.

## 2. Decisiones

| Tema | Decisión |
|------|----------|
| Proyecto para capturas y E2E | Datos geométricos dibujados para la prueba; nombre «Estudio de muestra» y sin dirección |
| Capturas del manual | Guardarlas en `docs/manual/img/`, en JPG y por debajo de 1 MB |
| Imágenes sueltas en la raíz | Ignorarlas en Git y bloquearlas en pre-commit, también si pesan menos de 1 MB |
| IA | Solo `AI_PROVIDER_MODE=mock`; ninguna llamada real |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| `e2e/test_e2e_studio.py` | B-121: crea un esquema sintético, genera un boceto en mock y comprueba desde Chromium que aparecen vista y medida; al activar la ajustada, se desmarca y oculta la vista anterior y vacía su medida; al desmarcar la última, vuelve la imagen normal |
| `docs/manual/img/` | Capturas nuevas con proyecto sintético: portada activa, indicaciones, descartes, casillas de Composición y comparativas con las medidas debajo |
| Manual | Actualizadas las referencias de capturas en Proyectos, Bocetos, Composición y Render Final; añadidas comparativas y galerías de descartados donde corresponde |
| `.gitignore` | Ignora imágenes PNG/JPG/JPEG/WebP sueltas en la raíz, incluidas extensiones en mayúsculas; `docs/` queda fuera |
| `.pre-commit-config.yaml` | El hook `forbid-data-dir` también bloquea esas imágenes raíz aunque estén por debajo del límite del hook de tamaño |
| `docs/pasos/BACKLOG.md` | Coma corregida en B-116; B-121 registrado como resuelto |
| Paso 51 | Estado actualizado a cerrado tras la fusión de la PR #73 |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run --group e2e pytest -q e2e` | ✅ 9 passed en Chromium, contra contenedores aislados y API en `mock` (176,74 s) |
| `uv run pytest` | ✅ 387 passed |
| Ruff | ✅ `uv run ruff check .` y `uv run ruff format --check .` |
| `uv run --group docs mkdocs build --strict` | ✅ Construcción correcta, sin enlaces de imagen rotos |
| pre-commit | ✅ Todos los hooks pasan; la regla cubre las rutas raíz y Git deja versionables las capturas bajo `docs/manual/img/` |
| Capturas | ✅ Revisadas visualmente; JPG en `docs/manual/img/`, todas menores de 130 kB y con datos sintéticos |
| Coste | ✅ 0 €; la instancia aislada informa `mock` y no recibe credenciales del `.env` |
| CI de la PR | Pendiente |

## 5. Estado final

⏳ En revisión — rama `feat/paso-52`, pendiente de revisión y merge por el usuario.

## 6. Pendiente / futuro

- B-116 sigue pendiente de la prueba real en Azure, con activación y coste anunciados previamente.
- B-117 (medir el zum del encuadre emparejando estructuras) permanece abierto.
