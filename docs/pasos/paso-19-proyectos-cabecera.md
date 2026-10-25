# Paso 19 — Proyectos y cabecera

## 1. Objetivo

Tercer paso del [plan de la versión 2.0.0](plan-version-2.md): mejoras de la pestaña Proyectos y
de la cabecera, independientes del Estudio nuevo. Sin llamadas reales.

## 2. Decisiones tomadas

| Entrada | Decisión |
|---------|----------|
| **B-025** Proyecto al iniciar | Opción A del usuario. Se mantiene el proyecto que recuerda el navegador. Si no hay ninguno (otro navegador, proyecto borrado o en la papelera), se activa el último actualizado. Al mover un proyecto a la papelera se pasa al siguiente más reciente |
| **B-026** Interfaz | Ya quedó en el Paso 17: nombre y descripción, con el mismo diseño de la pestaña |
| **B-027** Coste del proyecto | Desglose por rol en el resumen, del más caro al más barato. Debajo, el desplegable «Llamadas de IA (N)» con una tabla breve de fecha, rol, estado y coste: cabe en media pantalla sin cortar columnas. Muestra hasta 1 000 llamadas (máximo de la API); si hay más, lo indica el título. Como hasta ahora, incluye las simuladas y las marca «(sim.)» |
| **B-044** Miniatura | Lo más avanzado que exista: render final seleccionado → último render final → composición seleccionada → última composición → boceto seleccionado → primer boceto → primera referencia → imagen de relleno |
| **B-050** Cabecera | Proyecto → Backend → Modo, alineados a la derecha; los avisos de gasto, al final |

## 3. Implementación

| Archivo | Cambios |
|---------|---------|
| `frontend/ui/tabs/projects.py` | Proyecto por defecto (B-025); desplegable con las llamadas (B-027) |
| `frontend/ui/views.py` | Desglose por rol en `project_summary_md`, `calls_label` y orden de `header_html` |
| `frontend/ui/cost_views.py` | `project_calls_md`: tabla breve de llamadas |
| `frontend/ui/api_client.py` | `project_costs` pide las llamadas (`limit=1000`) |
| `frontend/ui/covers.py` | Prioridad de la portada (B-044) |
| `frontend/ui/theme.py` | Distintivos a la derecha; tabla de llamadas compacta |
| `e2e/test_e2e_projects.py` | Tras borrar, se activa otro proyecto en lugar de quedar sin proyecto |
| Paso 18 | Cerrado en su documento y en el índice |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 360 passed |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| Playwright en local (mock, sobre una copia de `data/`, puertos 8001/7861 para no tocar Docker) | ✅ 5/5 |
| Revisión visual con capturas | ✅ cabecera en el orden nuevo, Salón activo por defecto, desglose por rol y tabla de 24 llamadas sin cortes |
| CI de la PR #27 | ✅ lint y tests, gitleaks, Docker con newman y Playwright |

## 5. Estado final

⏳ En revisión — rama `feat/paso-19`, PR #27.

## 6. Pendiente / futuro

- Paso 20 (Costes IA): la pestaña de costes pasará a mostrar solo el gasto real (B-031). Habrá
  que decidir si el resumen del proyecto hace lo mismo.
