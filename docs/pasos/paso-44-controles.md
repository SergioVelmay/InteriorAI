# Paso 44 — Controles bloqueados

## 1. Objetivo

Paso añadido al [plan de la versión 4.1.0](plan-version-4-1.md) tras la revisión del Paso 43
(B-113): con «procesando» se bloqueaban los botones (Paso 42), pero aún se podían marcar «Usar la
auditoría» o «Usar el retoque», cambiar la calidad, el formato o las variantes, o escribir.

## 2. Decisión (usuario, 2026-11-02)

Todos los controles de la pestaña, bloqueados en el estado «procesando», como los botones.

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Bloqueo (`ui/locks.py`, `CONTROLS`) | Con el mismo criterio que los botones (un «procesando» a la vista o una confirmación abierta), se marcan con `data-iai-locked` los controles de la pestaña: casillas, opciones, deslizadores (también su número), desplegables, campos de texto y el lienzo del retoque. Sin tocar su `disabled`, que gobierna Gradio: se anulan en captura los clics, el arrastre, las teclas (salvo el tabulador) y lo que se escriba, pegue o suelte |
| Aspecto (`theme.CSS`) | Los controles bloqueados, atenuados y con el cursor de prohibido |
| Pruebas E2E (`e2e/conftest.py`) | Escribir, marcar y elegir archivo también esperan al desbloqueo, como los clics |
| Documentación | Manual (aviso de la portada), referencia de la interfaz y `docs/agent/gradio_ui.md` |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 375 |
| Navegador (simulación tras un proxy que anuncia Azure, red lenta; nunca se confirma) | ✅ Al abrir otra imagen en Bocetos, 18 controles bloqueados y atenuados: pulsar «Alta», el deslizador de variantes y escribir en las indicaciones no cambia nada; en Composición, «Usar la auditoría» tampoco. Con la confirmación de 8 bocetos abierta, lo mismo; al cancelar, todo vuelve a responder |
| Playwright de extremo a extremo (aplicación local en simulación) | ✅ 7 passed |
| `mkdocs build --strict` | ✅ |
| pre-commit | ✅ |

Coste real del paso: 0 €.

## 5. Estado final

⏳ En revisión — rama `feat/paso-44`.

## 6. Pendiente / futuro

- Paso 45: versión 4.1.0.
