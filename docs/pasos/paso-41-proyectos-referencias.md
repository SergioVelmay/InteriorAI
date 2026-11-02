# Paso 41 — Proyectos y referencias

## 1. Objetivo

Primer paso del [plan de la versión 4.1.0](plan-version-4-1.md): el proyecto que no aparecía al
crear dos seguidos (B-107) y la vista previa de la imagen al subir una referencia (B-108).

## 2. Diagnóstico de B-107

En los datos reales del usuario no faltaba ningún proyecto (los 6 de disco, en el índice; la
papelera, vacía): el segundo nunca llegó a crearse. Reproducido en local (simulación, red lenta
emulada en el navegador): al escribir el nombre del segundo proyecto mientras se crea el
primero, la respuesta del primero vacía el formulario y borra lo escrito; «Crear proyecto» con
el formulario vacío no crea nada. Con mala conexión, la espera es más larga y es fácil que pase.
Sin escribir durante la creación, los dos aparecen, también tras recargar.

El formulario de subir una referencia tenía el mismo problema durante la subida y el análisis
(hasta un minuto): las notas de la siguiente se perdían al vaciarlo.

## 3. Decisiones tomadas (usuario, 2026-11-02)

| Tema | Decisión |
|------|----------|
| Vista previa (B-108) | Encima de las **notas** del formulario de subir una referencia, del mismo ancho |
| Cancelar | Botón «Cancelar» junto a «Subir y analizar»; la imagen no se guarda si no se sube |

## 4. Implementación

| Parte | Cambios |
|-------|---------|
| Bloqueo inmediato (`ui/locks.py`, nuevo) | `lock_js(...)`: JS del evento que desactiva campos y botones en el mismo clic, sin esperar a la ida y vuelta al servidor (con la red lenta, el bloqueo del servidor llegaba segundos después) |
| Nuevo proyecto (B-107) | Al pulsar «Crear proyecto»: formulario bloqueado y botón «Creando…» (`lock_form`, en el navegador y en el servidor); al terminar, haya ido bien o no, se desbloquea |
| Subir una referencia (B-108) | Vista previa de la imagen elegida (`#iai-upload-preview`) entre el archivo y las notas, a todo el ancho; «Cancelar» vacía imagen y notas; mientras sube y analiza, formulario bloqueado y botón «Subiendo y analizando…» (`lock_upload`) |
| Copias temporales (`ui/uploads.py`, nuevo) | `discard_upload` borra la copia de Gradio (y su carpeta) al cancelar, al cambiar de imagen o al subirla, solo dentro de la carpeta de subidas de Gradio; `delete_cache=(3600, 86400)` en `gr.Blocks` borra cada hora las de más de un día |
| Manual | Proyectos (formulario bloqueado) y Referencias (vista previa, «Cancelar»), con la captura del formulario nueva |
| Documentación | Referencia de la interfaz y `docs/agent/gradio_ui.md` |

## 5. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ Tests nuevos (`test_ui_uploads.py`): solo se borran copias de Gradio, y nunca fuera de su carpeta; la cadena bloquear → crear → desbloquear del nuevo proyecto; vista previa, cambio de imagen, «Cancelar» y bloqueo al subir |
| Navegador (aplicación local en simulación, red lenta emulada) | ✅ A 0,3 s del clic el nombre y el botón ya están bloqueados («Creando…»); al terminar se desbloquean y el segundo proyecto se crea. La vista previa ocupa el ancho de las notas; «Cancelar» la oculta, vacía las notas y borra la copia temporal; al subir, formulario bloqueado y, al terminar, copia borrada |
| Playwright de extremo a extremo (aplicación local en simulación) | ✅ 6 passed |
| `mkdocs build --strict` | ✅ |
| pre-commit | ✅ |
| CI de la PR #59 | ✅ lint y tests, gitleaks, Docker con newman y Playwright, y la construcción de la documentación |

Coste real del paso: 0 €.

## 6. Estado final

✅ Cerrado — rama `feat/paso-41`, PR #59 revisada y mergeada por el usuario (2026-11-02), junto con
las de Dependabot #57 (`setup-uv`) y #58 (8 dependencias de Python, Gradio 6.31.0). Docker
reconstruido.

## 7. Pendiente / futuro

- Paso 42: botones bloqueados y apagados en todas las pestañas (B-110).
