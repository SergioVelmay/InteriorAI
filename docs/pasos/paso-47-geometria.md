# Paso 47 — Superponer el esquema 3D y medir la geometría

## 1. Objetivo

B-116, petición del usuario: sus proyectos parten de un esquema 3D de SketchUp (aristas negras,
colores planos, 3:2) como única referencia de perspectiva, encuadre y cámara, y le cuesta mucho
que bocetos, composiciones y renders respeten sus volúmenes. Su objetivo: superponer el esquema
sobre el render final y ver que cada volumen coincide. Este paso da la **vara de medir** (sin
coste); el laboratorio del Paso 48 probará cómo acercarse a ese objetivo.

## 2. Diagnóstico (datos reales, solo lectura)

| Proyecto | Bocetos | Composiciones | Renders | Retoques | Auditorías |
|----------|--------:|--------------:|--------:|---------:|------------|
| Getafe · Alzado Principal | 4 | 3 | 1 | 1 | no conforme, 77 |
| Getafe · Alzado Desayunero | 4 | 8 | 1 | 6 | no conforme, 65 |
| Getafe · Cocina y Desayunero | 12 | 4 | 8 | 1 | no conforme, 76 |
| Getafe · Cocina y Sofá Jattebo | 12 | 8 | 4 | 5 | no conforme, 76 y 71 |

Los retoques corrigen geometría (anchos de ventana, despiece, alturas y grosores, tiradores). Con
la medida de este paso, el render final seleccionado de «Cocina y Sofá Jattebo» coincide con el
esquema en un 24 % de sus aristas a ±3 px y un 43 % a ±8 px: el modelo cambió la cámara (el sofá
más grande y desplazado) y movió encimera, juntas, techo y puerta. El `PROMPT_ARCHITECT` gasta
unos 0,003 € por llamada (≈ 18.000 tokens de entrada y 2.300 de salida): hay margen para darle
más contexto (Paso 48).

## 3. Decisiones (usuario, 2026-11-03)

| Tema | Decisión |
|------|----------|
| Medir y superponer | Sí, primero; con OpenCV |
| Aristas | Las negras finas del esquema (no las superficies oscuras); en ráster (los segmentos vectoriales, si hacen falta, en el laboratorio). Un canto redondeado debe caer dentro del volumen recto |
| Postproducción | Ninguna: análisis sí, retocar las imágenes no |

## 4. Implementación

| Parte | Cambios |
|-------|---------|
| `ui/geometry.py` (nuevo, OpenCV) | Aristas del esquema: trazos casi negros finos (una apertura morfológica descarta las superficies oscuras rellenas) y cambios entre colores planos, sin la marca de agua de SketchUp. Fidelidad: parte de esas aristas con una arista estructural de la imagen (suavizada para que no cuenten las texturas) a ±3 y ±8 px, a la escala del esquema; ±8 px tolera cantos redondeados de pocos píxeles. Superposición: las aristas en rojo sobre la imagen, a su tamaño, con la opacidad elegida. Con caché |
| Interfaz | En Bocetos, Composición y Render final, bajo la imagen en grande: casilla «Superponer el esquema 3D» y opacidad; la superposición es una vista aparte (se puede descargar) y la imagen no cambia. Se mantiene al cambiar de imagen. Fidelidad en el título («Fidelidad al esquema 3D: 24 % a ±3 px · 43 % a ±8 px») y en el pie de cada miniatura («geometría 43 %») |
| Esquema | La imagen base de los bocetos: la referencia activa con la perspectiva marcada |
| Dependencia | `opencv-python-headless` en el frontend |

Referencia: el propio esquema contra sí mismo da 92 % a ±3 px y 94 % a ±8 px (detalles muy finos
que el detector de la imagen suaviza): es el techo práctico de la medida.

## 5. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 382 (nuevo `test_ui_geometry.py`: aristas finas sí y superficies oscuras no; fidelidad completa consigo mismo y menor al desplazar la geometría; superposición a la escala de la imagen) |
| Navegador (simulación, copia de los datos) | ✅ En «Cocina y Sofá Jattebo», pies con la geometría de cada render (un candidato llega al 59 %, el seleccionado tiene 40 %); la casilla cambia a la vista superpuesta, se mantiene al cambiar de imagen y se quita |
| Playwright de extremo a extremo | ✅ 8 passed |
| `mkdocs build --strict` | ✅ |
| pre-commit | ✅ |
| CI de la PR #67 | ✅ lint y tests, gitleaks, Docker (con OpenCV en el frontend) con newman y Playwright, y la construcción de la documentación |

Coste real del paso: 0 €.

## 6. Estado final

⏳ En revisión — rama `feat/paso-47`.

## 7. Pendiente / futuro

- Paso 48: laboratorio de geometría sobre una copia de «Cocina y Sofá Jattebo» (hasta 5 €), sin
  postproducción.
