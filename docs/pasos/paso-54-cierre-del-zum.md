# Paso 54 — Cerrar el zum del encuadre (B-117)

## 1. Objetivo

Cerrar [B-117](BACKLOG.md) dejando por escrito lo que se probó para medir el **zum** del encuadre
(cuánto más pequeña sale la escena generada que el esquema 3D), por qué ninguna vía funciona y qué
conviene hacer en su lugar. Decisión del usuario (2026-11-08): cerrarlo sin implementarlo, pero
documentado.

El desplazamiento del encuadre sí quedó medido y entregado en el [Paso 49](paso-49-encuadre.md);
lo que se cierra aquí es solo el multiplicador de escala.

## 2. Decisiones tomadas

| Tema | Decisión |
|------|----------|
| B-117 | **Cerrado sin implementar.** Cinco criterios de cuatro familias distintas han fallado; el resultado no compensa el esfuerzo |
| Acotar la escala a ±20 % | Descartado: acota el error del único criterio que seguía la verdad, pero su curva sigue siendo demasiado plana para poner un número en pantalla |
| Emparejar estructuras (segmentos) o usar un modelo | Descartado por el usuario: no se quieren modelos nuevos ni coste |
| Dónde queda la conclusión útil | En el manual (`docs/manual/consejos.md`): de qué vista de SketchUp conviene partir |
| El laboratorio | No se versiona código de la prueba: fue un ensayo de usar y tirar y este documento recoge sus números |

## 3. Lo que se probó

### 3.1. Los tres criterios del Paso 49 (contar píxeles cerca)

Recogidos en [Paso 49 §5](paso-49-encuadre.md#5-el-zum-por-qué-no-entra-todavía):

| Criterio | Por qué no vale |
|----------|-----------------|
| Cobertura del esquema | Degenera: encogerlo siempre «mejora», porque cabe entero en cualquier zona con detalle. Se iba al límite de la rejilla (x0,55) en casi todas las imágenes |
| Media armónica de ida y vuelta | Los dos sesgos se compensan en un punto que depende de la textura del render, no de la geometría: x1,00 en todo, y un render encogido a 0,80 seguía dando x0,98 |
| Cobertura dividida por la densidad de la zona | El único que sigue la verdad (x0,90 de base; encogido a 0,80 da x0,75, esperado 0,72), pero la curva es muy plana y ampliado a 1,20 se queda en x1,00 en vez de 1,08 |

### 3.2. Traslación por mitades

Medir el desplazamiento de cada mitad de la imagen por separado y sacar la escala de la
diferencia. Daba x0,47 para el original sin tocar y no seguía transformaciones conocidas: cada
mitad se desliza libremente hacia las regiones con más detalle.

### 3.3. Fourier-Mellin (log-polar + correlación de fase) — nuevo en este paso

Es el método de libro para sacar la escala global entre dos imágenes y no se había intentado. La
magnitud de la FFT no depende del desplazamiento, y en coordenadas log-polares un cambio de escala
se convierte en un desplazamiento que la correlación de fase sí sabe medir. Todo con OpenCV, que
ya es dependencia: **sin modelos nuevos y sin coste**.

Se midió contra escalas conocidas, separando el caso fácil (dos imágenes del mismo tipo) del caso
real del producto (esquema de líneas contra render):

| Prueba | x0,80 | x0,90 | x1,00 | x1,10 | x1,20 |
|--------|------:|------:|------:|------:|------:|
| Esquema **sintético** (tres rectángulos limpios) contra sí mismo | **0,801** | **0,902** | 1,000 | **1,099** | 1,000 ✗ |
| Esquema 3D **real** contra sí mismo | 1,149 ✗ | 1,501 ✗ | 1,000 | 1,000 ✗ | 1,216 |
| Boceto **real** contra sí mismo | 1,511 ✗ | 1,038 ✗ | 1,000 | 0,987 ✗ | 1,000 ✗ |
| **Esquema 3D contra el boceto** (el caso real; base x1,126) | 1,700 ✗ | 1,166 ✗ | — | 1,110 ✗ | 0,999 ✗ |

Con geometría sintética limpia acierta con un error menor de 0,003 (falla a x1,20, donde el
recorte se lleva una quinta parte del encuadre). Pero **con el esquema de SketchUp real ya falla
contra una copia escalada de sí mismo**, que es el caso más fácil posible.

La confianza que devuelve la correlación lo delata: 0,99 solo cuando las dos imágenes son
idénticas, y 0,02–0,14 en cuanto hay escala de por medio. No hay pico; está leyendo ruido.

La razón es la misma que tumbó a los tres criterios anteriores: un mapa de aristas real es
**textura densa**, no unas pocas estructuras. Su espectro lo domina la estadística del grano, y
redimensionar cambia esa estadística tanto como cambia la geometría.

## 4. Conclusiones

1. **No se puede medir el zum contando píxeles ni con correlación global.** Cinco criterios de
   cuatro familias (cobertura, simétrica, normalizada por densidad, traslación por mitades y
   Fourier-Mellin) fallan por el mismo motivo: comparan dos representaciones que no son la misma
   escena dibujada a otro tamaño, sino una interpretación distinta de ella. Haría falta emparejar
   estructuras (detectar segmentos y casarlos) o un modelo, y ambas cosas están descartadas.
2. **El número aportaba poco.** El zum **ya se ve** en la superposición ajustada: las aristas rojas
   salen mayores que la escena. La decisión del usuario (aceptar la imagen, descartarla o volver a
   generar) es la misma con el número que sin él.
3. **Conviene partir de esquemas con perspectivas convencionales.** Lo que sí reduce el problema de
   raíz es la vista de la que se parte. El laboratorio del
   [Paso 48](paso-48-laboratorio-geometria.md) ya lo había medido con tres vistas de la misma
   escena:

   | Vista de SketchUp | Fidelidad a ±8 px | La escena sale al |
   |-------------------|-------------------|-------------------|
   | Picada, tres puntos de fuga | 50–52 % | — |
   | Dos puntos de fuga, 50° (≈ 26 mm, angular) | 42–43 % | — |
   | Dos puntos de fuga, 60 mm | 48–53 % | 68–85 % |

   Los modelos **enderezan las verticales de todas formas** y **siempre abren el plano**. Partir de
   una vista que ya es la que el modelo va a dibujar —dos puntos de fuga, verticales rectas y una
   focal normal, no angular, como una fotografía de interiores al uso— le evita reinterpretar el
   encuadre, y lo que queda es un zum residual menor en vez de una reinterpretación completa. La
   vista angular (50°) es la peor de las tres: cuanto más forzada la perspectiva, más lejos queda
   el resultado.

## 5. Implementación

| Archivo | Cambio |
|---------|--------|
| `docs/pasos/paso-54-cierre-del-zum.md` | Este documento |
| `docs/pasos/paso-49-encuadre.md` | El cierre de §5 remite a este paso en vez de dejar el zum abierto |
| `docs/pasos/BACKLOG.md` | B-117 pasa a cerrado sin implementar |
| `docs/pasos/README.md` | Añade la fila del Paso 54 |
| `docs/manual/consejos.md` | Nueva sección «La vista del esquema 3D» con la conclusión 3, para el usuario |

Sin cambios de código: `frontend/ui/geometry.py` se queda como está tras el
[Paso 51](paso-51-portada-geometria.md).

## 6. Validación

La prueba de Fourier-Mellin se ejecutó en un laboratorio fuera del repositorio
(`%TEMP%`, con OpenCV y las funciones `sketch_edges()` y `_photo_edges()` de
`frontend/ui/geometry.py`), sobre el proyecto **«Laboratorio geometría 3 · Cocina y Sofá Jattebo
(dos puntos, 60 mm)»** y escalas conocidas aplicadas con `cv2.resize`. Los números de §3.3 son su
salida literal.

**Coste: 0 €.** No hubo ninguna llamada a IA; la aplicación siguió en `AI_PROVIDER_MODE=mock`.

Documentación: `uv run --group docs mkdocs build --strict`.

## 7. Estado final

✅ Cerrado — rama `feat/paso-54`.

## 8. Pendiente / futuro

Nada de B-117: queda cerrado. Si algún día se retoma, el camino sería emparejar estructuras
(segmentos del esquema contra segmentos de la imagen) o un modelo con control estructural, las dos
opciones que el usuario descartó.
