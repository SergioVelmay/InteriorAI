# Paso 36 — Manual de usuario

## 1. Objetivo

Quinto paso del [plan de la versión 4.0.0](plan-version-4.md): el manual de usuario de la web
pública (B-101), con un caso real hecho desde cero en la aplicación con la IA de Azure,
**«Cocina Abierta para Manual de Usuario»**.

## 2. Decisiones tomadas (usuario, 2026-10-27)

| Tema | Decisión |
|------|----------|
| Caso | Proyecto nuevo con las referencias de «Personalización Cocina Los Molinos», en modo `azure`; hasta 5,00 € (avisar al pasar de 3 €) |
| Punto de vista | El de la infografía con muchos muebles (la vista general del salón-comedor) |
| SketchUp | Solo medidas y distribución, **sin el desayunador** que está delante del cuerpo principal de la cocina |
| Cocina de referencia | Sus colores: gris antracita y madera |
| Piso vacío | Materiales de paredes, suelo y techo, ventanas, cortina, estor, vistas y barandilla |
| Composición | Quitar o cambiar muebles con colores y materiales que combinen con los de la cocina |
| Retoque | Solo una planta en maceta con la máscara (sin el perro del primer brief) |
| Render final | Día, atardecer y noche; queda seleccionado el de noche |
| Ejecución | Claude maneja la aplicación local en exclusiva durante las capturas (el usuario no la abre) |

## 3. Implementación

### El caso, en la aplicación real

Recorrido automatizado con Playwright sobre la aplicación en Docker (modo `azure`, 1920 × 1080),
con capturas de cada sección en cada estado (vacía, rellena, confirmación, procesando, resultado):

| Etapa | Qué se hizo |
|-------|-------------|
| Proyectos | Crear el proyecto con su descripción; edición; confirmación de la papelera (cancelada); resumen y llamadas |
| Referencias | 6 referencias con notas; fichas revisadas (en la infografía, fuera la cocina blanca); una referencia descartada, analizada de nuevo con otras notas y descartada otra vez |
| Bocetos | Dos tandas de 4 en calidad media (la segunda con indicaciones); confirmación de 8 variantes cancelada; boceto elegido con su trazabilidad |
| Composición | Auditoría con observaciones (no conforme, 78/100); composición con la auditoría y cambios de mobiliario; retoque con máscara (un olivo en maceta); otra composición desde la actual (un cuenco de naranjas) |
| Render final | Día, atardecer y noche a 4 MP; «Otra versión» del atardecer; panorámica 16:9 desde el render de día; seleccionado el de noche |
| Costes IA | Proyecto y todos los proyectos, registro filtrado por errores, detalle de una llamada y precios |

Las capturas se convierten a JPEG (calidad ajustada para quedar bajo 1 MB, la mayor 368 KB):
**81 imágenes, 9,2 MB**, en `docs/manual/img/`.

### Las páginas

| Página | Contenido |
|--------|-----------|
| `manual/index.md` | El caso en cuatro imágenes, qué se pidió, el recorrido y lo que costó por rol |
| `manual/proyectos.md` | Galería, crear (con la descripción del caso), editar, papelera y resumen |
| `manual/referencias.md` | Notas de las 6 referencias, receta y ficha, papel de cada referencia, activa o descartada, volver a analizar |
| `manual/bocetos.md` | Lo que recibe el modelo, opciones, confirmación de coste, qué pasa al generar, elegir y trazabilidad |
| `manual/composicion.md` | Auditoría, crear la composición, retoque con máscara (editor, zona, resultado y máscara enviada) y seguir mejorando |
| `manual/render-final.md` | Lo que recibe el modelo, opciones, día, atardecer y noche en pestañas, tiempo agotado, otra versión, desde el render actual y el elegido |
| `manual/costes.md` | Indicadores, gráficos, registro con filtros y CSV, detalle de una llamada, precios y todos los proyectos |
| `manual/consejos.md` | Descripción, notas, fichas, indicaciones por etapa, elegir bien y controlar el gasto |

La portada de la web (`docs/img/portada-render-final.jpg`) pasa a ser el render de noche del caso.

## 4. Gasto del caso

**1,5658 €** estimados con los precios de lista, en **29 llamadas** (1 error), el 2026-10-27:

| Rol | Llamadas | Coste |
|-----|----------|-------|
| `REFERENCE_ANALYST` | 7 | 0,2030 € |
| `PROMPT_ARCHITECT` | 10 | 0,0209 € |
| `FAST_DRAFT_MAKER` | 2 | 0,4809 € |
| `GEOMETRY_AUDITOR` | 1 | 0,2654 € |
| `COMPOSITION_BUILDER` | 3 | 0,2088 € |
| `REALISTIC_RENDERER` | 6 | 0,3867 € |

El primer render de noche agotó el tiempo (120 s, `FoundryTimeoutError`) y no se reintentó solo:
figura con 0,013 € (los megapíxeles de referencia). Para contrastar con la factura en el Paso 38
(B-098).

## 5. Hallazgos

| Hallazgo | Destino |
|----------|---------|
| En Bocetos, la estimación junto al botón («4 en calidad media») no cambia al mover **Variantes**; la confirmación sí calcula bien (8 → 0,284 €) | B-104 |
| En Costes IA, el aviso dice que las llamadas con error figuran a 0 €, pero un tiempo agotado del renderizador figura con el coste de las imágenes de referencia (0,013 €) | B-105 |
| El render al atardecer alargó la mesa y añadió una estructura; «Otra versión» lo resolvió | Documentado en el manual |

## 6. Validación

| Prueba | Resultado |
|--------|-----------|
| `mkdocs build --strict` | ✅ Sin avisos |
| Revisión visual (Playwright sobre la web construida) | ✅ Páginas, rejillas de imágenes y pestañas de los renders |
| Imágenes | ✅ Todas referenciadas; ninguna de más de 1 MB |
| `uv run pytest` | ✅ |
| pre-commit | ✅ |

## 7. Estado final

⏳ En revisión — rama `feat/paso-36`.

## 8. Pendiente / futuro

- B-104 y B-105, pequeños arreglos de la interfaz.
- Paso 37: comunidad del repositorio (B-102).
