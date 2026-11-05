# Paso 49 — El encuadre: medir y corregir el desplazamiento

## 1. Objetivo

Tercera parte de B-116. El [Paso 47](paso-47-geometria.md) dio la medida de fidelidad y el
[Paso 48](paso-48-laboratorio-geometria.md) mostró que la geometría se pierde en el primer salto
y que buena parte del desajuste no es de forma, sino de **encuadre**: la escena generada sale
desplazada (y más pequeña) que el esquema 3D. Este paso separa las dos cosas, para que el
porcentaje diga si el modelo dibujó mal los volúmenes o solo encuadró distinto.

Todo el paso es **sin coste**: solo lee imágenes ya generadas. Ninguna llamada a la IA.

## 2. Decisiones (usuario, 2026-11-04)

| Tema | Decisión |
|------|----------|
| Dos superposiciones | Dos casillas independientes, «tal cual» y «ajustada», con **una sola barra de opacidad** compartida; se pueden marcar las dos a la vez |
| El dato, sobre la imagen | En rojo, encima de la vista: en «tal cual», el porcentaje; en la ajustada, el desplazamiento horizontal, el vertical y el porcentaje con ese desplazamiento |
| Ordenar por fidelidad | No: el usuario mira los porcentajes y elige («esos % no lo son todo») |
| Tandas de 8 por defecto | No: ya existe el control «Variantes» (1 a 8) y lo sube él cuando quiere |
| Postproducción | Ninguna, como en los pasos anteriores: se mueven las aristas del esquema para medir, nunca la imagen generada |

## 3. Implementación

| Parte | Cambios |
|-------|---------|
| `ui/geometry.py` | `Alignment` (desplazamiento + fidelidad con él) y `alignment()`. Búsqueda en dos fases: correlación por FFT a baja resolución (todos los desplazamientos de una vez) y afinado a tamaño completo. Parte de «no mover nada», así **el ajustado nunca mide peor que el tal cual a ±8 px**, y solo se mueve si gana de verdad (`MARGIN`). La búsqueda maximiza el ±8 px, de modo que el ±3 px puede quedarse un punto por debajo. Desempate con la tolerancia fina (±3 px) para que, entre desplazamientos que a ±8 px empatan, gane el que ajusta mejor |
| `ui/geometry.py` | `overlay()` admite el encuadre y un rótulo: las aristas se dibujan movidas y el dato va en rojo sobre la imagen, con reborde oscuro para que se lea sobre cualquier fondo |
| Interfaz | En Bocetos, Composición y Render final: dos casillas («Superponer el esquema 3D» y «Superponerlo corrigiendo el desplazamiento del encuadre»), la opacidad compartida y dos vistas aparte, descargables |
| Arreglo | La superposición nunca engrosaba el trazo cuando la imagen es mayor que el esquema: se comparaba el ancho ya reescalado consigo mismo (`ui/geometry.py`, del Paso 47) |

El desplazamiento se da en píxeles a la escala del esquema, con el signo visto desde la escena:
«63 px a la izquierda» quiere decir que la escena sale corrida a la izquierda.

## 4. Validación

| Prueba | Resultado |
|--------|-----------|
| `uv run pytest` | ✅ 385 (tres nuevas en `test_ui_geometry.py`: recupera un desplazamiento conocido y se queda quieto cuando no lo hay; nunca mide peor que el esquema tal cual; la superposición mueve las aristas y escribe el rótulo) |
| Verdad conocida sobre un render real | ✅ Se desplaza un boceto real una cantidad conocida y se vuelve a medir: +90/+50 → detecta +90/+50; −120/0 → −116/−24 sobre su base; 0/−70 → +0/−70. Error de 2 a 4 px |
| Las tres copias del laboratorio (24 imágenes) | ✅ Sin excepción, el ajustado mejora o iguala a ±8 px: bocetos del 43–54 % al 50–60 %, composiciones del 43–53 % al 51–61 %, renders finales del 43–51 % al 48–54 %. De 4 a 8 puntos de media |
| Tiempo | ✅ 0,1–0,2 s por imagen, con caché |
| CI de la PR #70 | ✅ Lint y tests, gitleaks, Docker con newman y Playwright, y la construcción de la documentación |
| Interfaz | ✅ La aplicación construye las seis casillas y las seis vistas; el bloqueo de controles al procesar (B-113) las cubre sin tocar nada, porque su selector es genérico |

Coste real del paso: 0 €.

## 5. El zum: por qué no entra todavía

El laboratorio decía que la escena sale al 68–85 % de su tamaño, y en la superposición **se ve**:
las aristas rojas son mayores que la escena. El usuario pidió también el multiplicador de zum.
Se probaron tres criterios y ninguno es lo bastante fiable:

| Criterio | Qué hace | Por qué no vale |
|----------|----------|-----------------|
| Cobertura del esquema | Qué parte de las aristas del esquema cae sobre una de la imagen | Degenera: encogerlo siempre «mejora», porque cabe entero en cualquier zona con detalle. Se iba al límite de la rejilla (x0,55) en casi todas las imágenes |
| Media armónica de ida y vuelta | Además, qué parte de las aristas de la imagen queda cubierta | Los dos sesgos se compensan en un punto que depende de cuánta textura tenga el render, no de la geometría: daba x1,00 en todo, y al encoger un render real a 0,80 seguía diciendo x0,98 |
| Cobertura dividida por la densidad de la zona | Corrige el sesgo anterior por lo poblada que esté la región | Es el único que sigue la verdad (x0,90 de base; al encoger el render a 0,80 da x0,75, esperado 0,72), pero la curva es muy plana y con el render ampliado a 1,20 se queda en x1,00 en vez de 1,08 |

Medir el zum bien pide emparejar estructuras, no contar píxeles cerca. Como el desplazamiento sí
está validado y es útil por sí solo, este paso entrega eso y deja el zum **abierto** (B-117).

## 6. Estado final

✅ Cerrado — rama `feat/paso-49`, PR #70 revisada y mergeada por el usuario (2026-11-05). Docker
reconstruido y comprobado en el navegador: con las dos casillas marcadas salen las dos vistas, y
en «Cocina y Sofá Jattebo (dos puntos, 60 mm)» la composición pasa de 53 % a 61 % a ±8 px con un
desplazamiento de 4 px a la derecha y 24 px arriba.

## 7. Pendiente / futuro

- B-117: el multiplicador de zum del encuadre, con un método que emparejar estructuras.
- Paso 50: la geometría en los prompts (quitar «gran angular moderado» del render final y añadir
  el bloque de encuadre) y el esquema como base opcional de la composición.
