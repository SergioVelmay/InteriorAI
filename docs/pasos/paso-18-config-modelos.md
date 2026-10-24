# Paso 18 — Configuración de los modelos de IA

## 1. Objetivo

Segundo paso del [plan de la versión 2.0.0](plan-version-2.md). Se trata de asignar cada tarea
de texto al modelo adecuado y de hacer configurable el razonamiento por rol. También se
verifican con llamadas reales los parámetros de los modelos de imagen y se fija en el código su
especialización.

## 2. Decisiones tomadas

| Tema | Decisión |
|------|----------|
| Telemetría con `CONTEXT_MANAGER` | Se lee como `REFERENCE_ANALYST` sin reescribir el JSONL (solo admite añadir líneas), con un validador comentado en `TelemetryRecord` (decisión del usuario) |
| `.env` del usuario | Lo actualiza Claude, alineado con `.env.example` (mismas secciones, orden y comentarios), sin tocar la clave ni el endpoint (decisión del usuario) |
| Llamadas reales | Autorizadas para todo el paso sin confirmar cada una; avisar solo por encima de 1 € (decisión del usuario) |
| Nombres de las variables de razonamiento | `PROMPT_ENGINEER_REASONING_EFFORT` y `REFERENCE_ANALYST_REASONING_EFFORT`, junto a la `GEOMETRIC_AUDITOR_REASONING_EFFORT` existente (mismo patrón `<ROL>_…`) |
| Comparativa luna/sol (B-052) | Se hará en el Paso 21, según el plan |

## 3. Implementación

| Commit | Cambios |
|--------|---------|
| **Cierre del Paso 17** | Documento e índice |
| **B-052 y B-053** | `CONTEXT_MANAGER` pasa a `REFERENCE_ANALYST` (rol, `DEPLOYMENT_ROLE_…`, `pipelines/reference_analyst.py` y su prompt). `.env.example`: `PROMPT_ENGINEER` usa luna y `REFERENCE_ANALYST` usa sol. Se añade `ReasoningSettings` y `Settings.reasoning_effort(role)`: el cliente envía `reasoning.effort` en los tres roles de texto (`medium` por defecto). `python -m shared` muestra el esfuerzo de cada rol |
| **B-037 y B-041** | Solo `STRUCTURAL_COMPOSER` admite máscara (`MASK_ROLE`); en los demás roles de imagen, el cliente rechaza la máscara antes de llamar a Azure. No se envía `input_fidelity` (ver la validación). El smoke deja margen de tokens al razonamiento y genera dos imágenes con la misma semilla |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 359 passed |
| `uv run ruff check .` / `ruff format --check` | ✅ |
| `python -m shared` con el `.env` nuevo | ✅ luna para los prompts, sol para las fichas, `medium` en los tres roles; listo para `azure` |
| Smoke real (`python -m app.foundry.smoke`) | 7 de 8 correctas; la llamada a sunburst con `input_fidelity` falló (ver abajo) |
| Brief e indexación reales sobre una **copia** de `data/` (proyecto Salón) | ✅ Ficha correcta con sol (5,1 s; 223 tokens de salida, 0 de razonamiento; 0,0052 €). Brief correcto con luna (13,5 s; 1 787 tokens de salida, de ellos 982 de razonamiento; 0,0011 €), dentro del tope de 6 000 |
| CI de la PR #26 | ✅ lint y tests, gitleaks, Docker con newman y Playwright (al segundo intento: el Dockerfile aún comprobaba el prompt `context_manager`) |

Hallazgos de las llamadas reales:

- **Razonamiento:** luna y sol aceptan `reasoning.effort=medium`. Luna razona en el brief (55 %
  de la salida) y sigue costando una milésima de euro; sol no razonó en ninguna de las dos
  pruebas. No hace falta subir los topes de tokens.
- **`input_fidelity` en sunburst:** el despliegue lo rechaza con un 400 («does not support the
  'input_fidelity' parameter»). Se quita. Sin el parámetro, el retoque con máscara conserva lo
  que queda fuera de la zona (prueba: sofá añadido en la zona marcada, resto intacto).
- **Semilla en FLUX:** el despliegue de Azure acepta `seed` pero no la respeta. Tres imágenes con
  la misma semilla y el mismo prompt salieron distintas: se parecen en la escena, pero cambian la
  ventana, el sillón y el encuadre. La respuesta tampoco devuelve la semilla. Esto afecta a la
  decisión de B-041 y al Render Final (B-051, Paso 24), donde la semilla debía servir para sacar
  versiones de una imagen. Se decidirá con el usuario antes del Paso 24.

Coste real del paso: unos 0,10 € (smoke 0,058 €, semillas y retoque sin `input_fidelity`
0,025 €, ficha y brief 0,006 €).

## 5. Estado final

⏳ En revisión — rama `feat/paso-18`, PR #26. **Después del merge hay que reconstruir Docker:** la
variable `DEPLOYMENT_ROLE_CONTEXT_MANAGER` ya no existe en el `.env`, así que la imagen anterior
no arrancaría en modo `azure`.

## 6. Pendiente / futuro

- B-052: comparativa luna/sol de fichas y prompts (Paso 21).
- B-037: el reparto de usos por pestaña del Estudio (Pasos 22 a 24).
- B-041 / B-051: decidir qué hacer con las versiones del render final, ya que la semilla de
  FLUX no es reproducible en Azure.
