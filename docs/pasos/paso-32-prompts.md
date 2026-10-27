# Paso 32 — Prompts del PROMPT_ARCHITECT más precisos

## 1. Objetivo

Revisar juntos los prompts de bocetos, composición y render final (B-054) aprovechando que el
PROMPT_ARCHITECT (luna) es muy barato y que el usuario ha subido su razonamiento a `high`: más
contexto, más detalle y más razonamiento para que los prompts sean más precisos (B-094 a B-097).

## 2. Decisiones tomadas (usuario)

| Tema | Decisión |
|------|----------|
| Tope de salida | Subirlo (con `high`, el razonamiento cuenta dentro del tope): 32 000 tokens |
| Medidas que faltan o no cuadran | El PROMPT_ARCHITECT razona con las medidas estándar del mercado de vivienda: unos centímetros de diferencia no se notan en una imagen |
| Dudas | Resolverlas de forma práctica, como un interiorista profesional, pensando en el propósito de la aplicación (hacerse una idea de los espacios, combinar mobiliario, integrar muebles de catálogo, ser fiel a los esquemas 3D); a `open_questions` solo lo que necesite al usuario |
| Historial | Pasar el historial de la cadena y las generaciones anteriores de la etapa; el coste de luna no es un problema |
| Longitud de los prompts | Sin límites propios que resten precisión: los que necesite, dentro de lo que admite cada modelo |
| Llamadas reales | Autorizadas; avisar solo por encima de 1 € |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| Tope y timeout (B-097) | `MAX_OUTPUT_TOKENS` de 6 000 a 32 000. Nuevo `PROMPT_ARCHITECT_TIMEOUT_S` (300 s por defecto; `Settings.timeout_for(role)`, como el del auditor) |
| Criterios comunes (B-097) | `prompt_criterios.md`, que se añade al prompt de cada etapa (versión `etapa@hash+prompt_criterios@hash`): propósito de la aplicación; medidas (usuario > cota de imagen > estimada; a igualdad, la referencia de perspectiva o geometría; si faltan o no cuadran, estándar de mercado, contado en `interpretation` y nunca como cota exacta); dudas resueltas como interiorista; historial (las decisiones de diseño se conservan, la luz o el ambiente pedidos antes no se heredan); distribución de izquierda a derecha anclada a la imagen; redacción en frases completas, sin listas de cotas; repaso final antes de responder |
| Prompts de etapa | Bocetos y composición: 150-600 palabras (retoque, 60-250); render final: 120-300, en positivo y con lo importante primero (FLUX.2 no tiene prompt negativo y atiende más a lo que va primero). `interpretation` más completa (medidas adoptadas y dudas resueltas); `open_questions` solo para lo que necesite al usuario, como propuesta concreta |
| Más contexto (B-094, B-095) | El resumen del análisis de cada referencia; «Historial de la imagen de partida» (de dónde viene: lo que se entendió en cada etapa, los retoques pedidos y el prompt de la imagen de partida); «Generaciones anteriores de esta etapa» (la seleccionada y la última, con su prompt, lo entendido y sus dudas) |
| Imágenes al escritor (B-096) | A 1 536 px (antes 1 024) y con `detail: high` (`InputImage.detail`), para leer cotas y rótulos |
| `Dockerfile` | El build comprueba también los prompts del escritor y los criterios |
| `AGENTS.md` | Regla 6: en los prompts, las medidas que falten o no cuadren pueden ser las estándar del mercado, siempre como aproximadas y explicadas al usuario |

## 4. Validación

Banco del PROMPT_ARCHITECT (`writer_bench.py`, fuera del repositorio): escribe los prompts de
cuatro escenarios con las mismas entradas que la aplicación, sin generar imágenes, sobre una
copia de «Personalización Cocina Los Molinos» y con el `.env` del usuario (`high`).

| Escenario | Antes (prompts de la 3.0.0) | Después |
|-----------|-----------------------------|---------|
| Bocetos | 102 s, razonamiento 12 638 tokens (con el tope de 6 000 habría fallado), 209 palabras telegráficas («bar 310×40 cm, traced heights 93/106…»), 2 dudas | 50-65 s, razonamiento 4 400-5 800, 550-680 palabras en frases completas y de izquierda a derecha, 0 dudas |
| Composición desde el boceto, con auditoría | 25 s, 224 palabras, las mismas 2 dudas | 38-53 s, 500-560 palabras, 0 dudas |
| Composición desde la composición | 15 s, 191 palabras, las mismas 2 dudas | 30-59 s, 450-630 palabras, conserva el frigorífico de acero del retoque, 0 dudas |
| Render final | 14 s, 181 palabras | 12-15 s, 230-250 palabras, conserva el retoque; sin indicaciones, luz de día (antes heredaba la «golden hour» del render seleccionado) |

Las dos dudas que se repetían en todas las generaciones (cinco altos de 60 cm frente a 4 × 60 +
50; desayunador a 90 frente a 93/106 cm) quedan resueltas: se adopta lo que escribió el usuario
y se interpretan 93 y 106 como cotas de partes distintas del desayunador.

Imágenes reales sobre la copia (comparaciones y prompts de antes y después en `InteriorAI-capturas/etapa-07-paso-32/`, fuera del repositorio):

| Prueba | Resultado |
|--------|-----------|
| 4 bocetos en calidad media (0,199 €) | ✅ Más coherentes entre sí que los del Paso 28 (misma distribución en las cuatro), limpios y con lo marcado; el encuadre sigue algo más abierto que el del esquema, como antes |
| Composición desde el boceto seleccionado, con auditoría (0,062 €) | ✅ Limpia y con las correcciones (frigorífico de acero, lamas, sin el mobiliario del salón); encuadre parecido al del Paso 28 |
| Render final «golden hour» desde la composición seleccionada (0,076 €) | ✅ Más fiel a la composición que el render final seleccionado (que cambió la placa de inducción por fuegos de gas) |
| `uv run pytest` | ✅ 386 passed |
| `uv run ruff check .` / `ruff format --check` / pre-commit | ✅ |
| Postman en local (mock) | ✅ 53 peticiones, 96 comprobaciones |
| Playwright en local (mock), Chromium y Edge | ✅ 6/6 |

Coste real del paso: 0,38 € (18 llamadas: 12 del PROMPT_ARCHITECT, 0,04 €, y 3 de imagen).

## 5. Estado final

⏳ En revisión — rama `feat/paso-32`.

## 6. Pendiente / futuro

- Con el uso real: vigilar la latencia del PROMPT_ARCHITECT con `high` (hasta 65 s en bocetos)
  y la longitud de los prompts (los modelos aprovechan todo el margen).
