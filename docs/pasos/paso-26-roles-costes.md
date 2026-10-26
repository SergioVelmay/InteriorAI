# Paso 26 — Roles y Costes IA

## 1. Objetivo

Primer paso del [plan de la versión 3.0.0](plan-version-3.md): renombrar los roles de IA
(B-057), contar el gasto por el rol que hoy tiene cada despliegue y rehacer los gráficos de
Costes IA con colores vivos y una leyenda común (B-080, B-081).

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Nombres | `PROMPT_ENGINEER` → `PROMPT_ARCHITECT`, `PHOTOREALISTIC_RENDERER` → `REALISTIC_RENDERER`, `FAST_DRAFT` → `FAST_DRAFT_MAKER`, `STRUCTURAL_COMPOSER` → `COMPOSITION_BUILDER`, `GEOMETRIC_AUDITOR` → `GEOMETRY_AUDITOR`; `REFERENCE_ANALYST` se queda |
| `.env` | **Solo los nombres nuevos** (sin aceptar los antiguos): versión **3.0.0**. La aplicación avisa si encuentra un nombre anterior, sin usarlo |
| Datos guardados | La telemetría y las imágenes se leen con los nombres nuevos, sin reescribirse (como `CONTEXT_MANAGER` en el Paso 18) |
| Costes por modelo | Cada llamada cuenta en el rol que **hoy** tiene su despliegue; una serie por rol (6). Casos límite: el mock nunca aparece (Costes IA es solo gasto real); un despliegue que ya no está asignado suma en el rol guardado (con su nombre actual); si dos roles comparten despliegue, manda el rol guardado. Registro, filtros y gráficos con el rol actual; el CSV añade «Rol en la llamada» |
| Colores | Verde `REFERENCE_ANALYST`, morado `PROMPT_ARCHITECT`, azul `FAST_DRAFT_MAKER`, amarillo `COMPOSITION_BUILDER`, naranja `REALISTIC_RENDERER`, rojo `GEOMETRY_AUDITOR` |
| Archivos de la v1 | `prompt_engineer.py`, `prompt_engineer.md` y `geometric_auditor.md` conservan su nombre: desaparecen con B-056 |
| Llamadas reales | Ninguna: `python -m shared` confirma el `.env` sin coste |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Roles | Enum `Role` y todas sus apariciones (código, tests, prompts de sistema, Postman, docs, `.env.example`, Dockerfile y `CLAUDE.md`); campos de `DeploymentSettings`, `ReasoningSettings` y el prefijo `GEOMETRY_AUDITOR_` de `AuditorSettings`. El historial (`docs/pasos`, versiones publicadas del CHANGELOG) no se toca |
| Datos antiguos | `shared.roles.RENAMED_ROLES` y `current_role`: validadores `before` en `TelemetryRecord.role` y `RenderRecord.role` |
| Variables antiguas | `Settings.legacy_env` (`legacy_env_vars`: entorno y `.env`); aviso en el registro del backend al arrancar, en `python -m shared` y en el error de configuración del modo `azure` |
| Costes (backend) | `summary.current_roles(settings)` (despliegue → rol actual) y `assign_current_roles`; `CostRecord.call_role`; `by_role` con el despliegue actual en `label`; nuevos `role_deployments`, `by_day_role` y `by_project_role`; fuera `by_role_deployment`. La cadena de costes de una imagen usa el mismo mapeo |
| Costes IA (interfaz) | `ROLE_COLORS` con seis colores vivos; `legend_html` (leyenda común, al 50 %) junto a «Coste por rol» (al 50 %, sin leyenda); «Coste por día» y «Coste por proyecto» apilados por rol a ancho completo (1160 px), sin leyenda; el detalle de una llamada muestra «Rol en la llamada» si cambió; el CSV, su columna |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 380 passed |
| `uv run ruff check .` / `ruff format --check` / pre-commit | ✅ |
| Postman en local (mock) | ✅ 53 peticiones, 96 comprobaciones |
| Playwright en local (mock) | ✅ 5/5 |
| Costes IA con una copia de los datos reales (mock) | ✅ Seis series; las llamadas antiguas aparecen con los nombres nuevos y las de la comparativa luna/sol del Paso 21 suman en el rol que hoy usa cada modelo |
| Llamadas reales | No hacen falta |
| CI de la PR #38 | ✅ lint y tests, gitleaks, Docker con newman y Playwright |

## 5. Estado final

⏳ En revisión — rama `feat/paso-26`, PR #38. Tras el merge: renombrar las variables del `.env` local
(lo hace Claude, sin tocar los valores), reconstruir Docker y comprobar `python -m shared`.

## 6. Pendiente / futuro

- Paso 27: estilo común, Proyectos y Referencias.
