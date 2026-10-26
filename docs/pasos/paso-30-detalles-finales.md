# Paso 30 — Detalles finales

## 1. Objetivo

Quinto paso del [plan de la versión 3.0.0](plan-version-3.md): los detalles que el usuario vio al
revisar la aplicación tras el Paso 29 (O-26 a O-33 → B-082 a B-089), antes de publicar la 3.0.0
(Paso 31). Sin llamadas reales: todo es de interfaz.

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Proyectos (B-082 a B-084) | Sin «Actualizar» (la pestaña se recarga al entrar); «Referencias activas: 4 de 4»; «SÍ» / «NO» en mayúsculas |
| Composición (B-085, B-086) | Sin ①, ② y ③; «Retoque de la composición seleccionada (opcional)»; «Crear composición» en este orden: apoyos, calidad y formato, casillas, indicaciones, imágenes de partida (1/4) y botones |
| Render Final (B-086) | Imágenes de partida a 1/4, como en Composición |
| Trazabilidad (B-088) | Un rótulo como el del prompt para las imágenes enviadas y el coste de la cadena al final del todo |
| Costes IA (B-089) | Siempre el ancho de las demás pestañas |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Proyectos | Fuera el botón y su evento; `project_summary_md`: «**4 de 4**» y «**SÍ**/**NO**» |
| Composición | Acordeones sin número; «Crear composición» reordenado; `.iai-half .iai-thumbs` a 2 por fila (1/4 de la página) en Composición y Render Final |
| Editor de máscara (B-087) | El icono de las circunferencias también en el deslizador de la goma (el selector ya no depende de `.size_picker`, que solo tenía el del pincel); la mano (solo activa con la imagen ampliada) en gris y, activa, en blanco y sin la transparencia de Gradio, para que se vea qué herramienta hay (con ella no hay pincel, goma ni tamaño); al elegir la mano se cierra el deslizador del tamaño (Gradio lo volvía a abrir al volver al pincel); el botón del tamaño con color fijo (no es una herramienta); «Deshacer» y «Ajustar a la pantalla» en español |
| Trazabilidad (B-088) | La galería pasa a «Imágenes enviadas al modelo de imagen» (incluye la imagen de partida y, en un retoque, la máscara); el coste de la cadena, en su propio bloque (`#iai-chain-{etapa}`) debajo de ella |
| Costes IA (B-089) | `.gradio-container` con `width: 100%`: el contenedor tenía solo un ancho máximo y se ajustaba a su contenido (1289 px frente a 1440 px en una pantalla de 1920 px) |

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 383 passed |
| `uv run ruff check .` / `ruff format --check` / pre-commit | ✅ |
| Postman en local (mock) | ✅ 53 peticiones, 96 comprobaciones |
| Playwright en local (mock), Chromium y Edge | ✅ 6/6 |
| Editor de máscara (Playwright, clics reales) | ✅ Goma → tamaño → pincel → tamaño → acercar → mano → pincel → tamaño → mano → goma → alejar → goma → tamaño → pincel: la herramienta activa siempre visible, las circunferencias en los dos deslizadores y el deslizador sin reabrirse solo |
| Ancho de la página (1920 y 2560 px) | ✅ 1440 px en todas las pestañas y en los dos alcances de Costes IA |
| Revisión visual (mock, copia de «Personalización Cocina Los Molinos») | ✅ Proyectos, Composición, Render Final y la trazabilidad |
| CI de la PR #42 | ✅ lint y tests, gitleaks, Docker con newman y Playwright |

Coste real del paso: 0 €.

## 5. Estado final

⏳ En revisión — rama `feat/paso-30`.

## 6. Pendiente / futuro

- Paso 31: capturas del README (B-023) con el caso de demostración del usuario y publicación de
  la 3.0.0.
