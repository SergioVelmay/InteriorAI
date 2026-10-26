# Paso 29 — Composición y Render Final

## 1. Objetivo

Cuarto paso del [plan de la versión 3.0.0](plan-version-3.md): pulir Composición y Render Final
(editor de máscara, secciones opcionales plegables, auditoría, prompt y títulos de las imágenes),
B-071 a B-078. Sin llamadas reales: todo es de interfaz.

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Secciones plegables (B-074) | ① Auditoría y ② Retoque empiezan cerradas; ① se abre sola si el boceto seleccionado ya tiene una auditoría, solo al abrir el proyecto o la pestaña |
| Tamaño con proporción (B-078) | En las tres pestañas, «2448×1632 (3:2)»; la calidad no aparece en el render final (el renderizador no la tiene) |
| Aviso del retoque (B-073) | «Con el retoque, las indicaciones solo actúan dentro de la zona pintada; para cambios globales, genera sin retoque» |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Iconos del editor (B-071) | La herramienta activa en blanco y las demás en gris (Gradio lo hacía al revés); lápiz y goma de 20 px; el tamaño, dos circunferencias de trazo fino (CSS), también dentro de su deslizador, donde Gradio repetía el icono de «prohibido» |
| Etiquetas del editor | Gradio traducía sus `aria-label` según el idioma del navegador y el CSS dependía de ellas: se fijan en español en `theme.GRADIO_TEXTS` (`image_editor.*`: «Pincel», «Goma», «Tamaño del pincel»…) |
| Rueda del ratón (B-072) | `FORCE_DARK_JS` intercepta la rueda sobre el lienzo antes que Gradio: la página se desplaza y el zoom queda en sus botones |
| Aviso del retoque (B-073) | `#iai-retouch-hint`, visible solo con «Usar el retoque» marcado |
| Secciones plegables (B-074) | `gr.Accordion` `#iai-audit-section` y `#iai-retouch-section`; `refresh_all` abre ① si el boceto seleccionado tiene auditoría. El editor se vuelve a montar también al desplegar ② |
| Tabla de la auditoría (B-075) | Sin partir palabras y la primera columna con ancho mínimo |
| Coste de la cadena (B-076) | «fichas de referencias, etapas, retoques y auditorías…», sin «brief» |
| Prompt enviado (B-077) | Con ajuste de línea (`pre-wrap`), sin desplazamiento horizontal |
| Títulos de las imágenes (B-078) | `size_label`: «1536×1024 (3:2)» (sin proporción si no es sencilla, p. ej. 1920×1088); «calidad» solo si la imagen la tiene |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 383 passed (nuevo: `size_label` y título del render final sin calidad; coste de la cadena sin «brief») |
| `uv run ruff check .` / `ruff format --check` / pre-commit | ✅ |
| Postman en local (mock) | ✅ 53 peticiones, 96 comprobaciones |
| Playwright en local (mock), Chromium y Edge | ✅ 6/6. Ahora despliegan ① y ② (`UI.expand`, que espera a que termine la carga de la pestaña) y comprueban la rueda sobre el lienzo, el aviso del retoque y la etiqueta «Tamaño del pincel» |
| Revisión visual (mock, copia de «Personalización Cocina Los Molinos») | ✅ Iconos del editor y del deslizador, ① abierta por tener auditoría, tabla sin palabras partidas, aviso, prompt ajustado y títulos de las tres pestañas |

Coste real del paso: 0 €.

Detalle conocido: si se despliega ① en el primer segundo tras entrar en la pestaña, la carga de
la pestaña puede volver a plegarla (fija su estado inicial al terminar).

## 5. Estado final

⏳ En revisión — rama `feat/paso-29`.

## 6. Pendiente / futuro

- Paso 30: capturas del README (B-023) con el caso de demostración del usuario y publicación de
  la 3.0.0.
