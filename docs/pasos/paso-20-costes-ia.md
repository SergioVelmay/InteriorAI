# Paso 20 — Costes IA

## 1. Objetivo

Cuarto paso del [plan de la versión 2.0.0](plan-version-2.md): la pestaña de costes pasa a
mostrar solo el gasto real. Sus gráficos ganan una leyenda legible, el registro de llamadas
ofrece el detalle de cada una y la tabla de precios separa las tarifas en columnas. Sin
llamadas reales.

## 2. Decisiones tomadas

| Tema | Decisión del usuario |
|------|----------------------|
| Gráficos (B-032) | **Altair** con `gr.Plot` (opción A): los gráficos nativos de Gradio no permiten una leyenda vertical sin recortes ni etiquetas en dos líneas |
| CSV del registro | **Todas las columnas**, también las que la tabla no muestra (petición, error, caché, desglose…): «toda la info es importante aunque no se muestre» |
| Resumen del proyecto | También **solo gasto real**, por coherencia con Costes IA |
| E2E | En la CI (datos nuevos, todo simulado) la pestaña no tiene gasto real que mostrar. La E2E comprueba ese estado, el alcance global y los precios. Los gráficos, el registro, el detalle y el CSV con datos se prueban con tests unitarios |

La pestaña muestra la **telemetría guardada**, sea cual sea el modo actual. Con los datos
locales del usuario (33 llamadas reales) se ve completa también en `mock`. Lo único que no se
muestra son las llamadas simuladas, que no tienen coste.

## 3. Implementación

| Entrada | Cambios |
|---------|---------|
| **B-031** | Pestaña «Costes IA» sin título ni casilla «Incluir simulación»; pide siempre `include_simulated=false` (la API conserva el parámetro). El resumen del proyecto hace lo mismo |
| **B-032** | `role_chart`, `day_chart` y `project_chart` (Altair, tema oscuro, ancho fijo: `width="container"` deja el gráfico vacío en `gr.Plot`). Series «ROL (despliegue)», con colores del rol y más claros si un rol ha usado varios despliegues. Leyenda debajo, un elemento por línea y sin recortar. En el gráfico por rol, etiquetas en dos líneas y casi verticales; en los gráficos por día y por proyecto, se giran solo si no caben. Backend: `CostSummary.by_role_deployment` |
| **B-033** | Tabla: Fecha · Proyecto (con todos los proyectos) · Rol · Despliegue · Estado (✓/error) · Coste · Latencia · Tokens entrada/salida · MPx generados/de referencia, con anchos ajustados y sin cortar palabras. Al seleccionar una fila, el panel de detalle muestra la operación, el error, el coste con su desglose y tarifa, los tokens (caché, texto, imagen, razonamiento), los MPx, la petición y el id. CSV con 23 columnas |
| **B-034** | Precios: Despliegue · Tipo · Tarifa 1 · Tarifa 2 · Tarifa 3 · Unidades (`€/M tokens`, `€/MPx`) |

Dependencia nueva del frontend: `altair` (Vega-Lite, la misma base que los gráficos nativos).

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 362 passed |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Playwright en local (mock, sobre una copia de `data/`) | ✅ 5/5 |
| Revisión visual con los datos reales copiados (33 llamadas) | ✅ Tras varias iteraciones: gráficos con leyenda completa, tabla sin desplazamiento ni palabras partidas, detalle de una fila |
| Imagen Docker del frontend con Altair | ✅ se construye |
| CI de la PR #28 | ✅ lint y tests, gitleaks, Docker con newman y Playwright (al segundo intento: faltaba `by_role_deployment` en la comprobación de Postman) |

## 5. Estado final

⏳ En revisión — rama `feat/paso-20`, PR #28.

## 6. Pendiente / futuro

- Ninguno propio del paso.
