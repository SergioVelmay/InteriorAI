# Paso 25 — Versión 2.0.0

## 1. Objetivo

Último paso del [plan de la versión 2.0.0](plan-version-2.md): documentación de la v2, revisión de
las dependencias pendientes, CHANGELOG, etiqueta y Release.

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Capturas del README (B-023) | Se publica la 2.0.0 **sin capturas**. El usuario probará la aplicación con un ejemplo completo y sin marcas, hará ajustes estéticos y después Claude recogerá las capturas con Playwright, solo mirando (sin acciones de IA ni cambios de selección), para una versión menor posterior |
| Compatibilidad con la v1 | Se **mantiene** en la 2.0.0, porque los datos reales tienen imágenes de la v1. Su retirada queda en el backlog (**B-056**) |
| Fecha | 2026-10-25 para el CHANGELOG y la Release |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Versión | `2.0.0` en los cuatro `pyproject.toml` (y en `/health`), `uv.lock` actualizado |
| README | Introducción, flujo (diagrama), roles y costes de la v2, medidos en las pruebas reales de los Pasos 21-24; nota de migración desde la 1.0.0 |
| CHANGELOG | «Sin publicar» pasa a `[2.0.0] — 2026-10-25`, con un resumen y la nota de migración |
| Documentación | `AGENTS.md` (brief del proyecto y regla 6 sin briefs), estado de `docs/agent/*`, plan de la v2 completado, índice de pasos y cierre del Paso 24 |
| Dependencias (B-024) | Gradio 6.30.0, la última publicada, sigue exigiendo `pillow<13`: se mantiene el `override-dependencies` de Pillow 13 y B-024 sigue abierto. Sin alertas de Dependabot abiertas |
| Backlog | B-056 nuevo (retirar la compatibilidad con la v1); B-023 y B-024, con su estado actualizado |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 371 passed |
| `uv run ruff check .` / `ruff format --check` / pre-commit | ✅ |
| Postman y Playwright en local (mock) | ✅ 53 peticiones y 96 comprobaciones; 5/5 en Edge; `/health` con la versión 2.0.0 |
| Llamadas reales | No hacen falta |
| CI de la PR #33 | ✅ lint y tests, gitleaks, Docker con newman y Playwright |

## 5. Estado final

⏳ En revisión — rama `feat/paso-25`, PR #33. Tras el merge: etiqueta `v2.0.0` y GitHub Release (con el
OK del usuario justo antes) y Docker reconstruido.

## 6. Pendiente / futuro

- B-023: capturas del README tras las pruebas y los ajustes estéticos del usuario (versión menor).
- B-024: quitar el `override-dependencies` cuando Gradio admita Pillow 13.
- B-056: retirar la compatibilidad con la v1.
