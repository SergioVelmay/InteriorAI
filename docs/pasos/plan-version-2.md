# Plan de acción — InteriorAI 2.0.0

Aprobado por el usuario el 2026-10-24. **Completado el 2026-10-25** (Pasos 17 a 25,
PRs #25 a #33; las llamadas reales, en el documento de cada paso). Aborda las 32 entradas
abiertas del [backlog](BACKLOG.md): B-023, B-024 y B-025 a B-054.

## Por qué 2.0.0

Cambian el modelo de datos (campos del proyecto, tipos de imagen, estados), el flujo (del brief
aprobado a pestañas con selección única) y la API: los datos actuales no son compatibles sin
migrar. Versión mayor según SemVer.

## Criterio de orden

1. Cimientos: datos y configuración de IA, de los que depende todo.
2. Mejoras de interfaz independientes: Proyectos y Costes IA.
3. Referencias: el Estudio nuevo se alimenta de sus recetas y selecciones.
4. Estudio, pestaña a pestaña, en el orden del flujo: Bocetos → Composición → Render Final.
5. Cierre y publicación.

Cada paso: explicación y OK del usuario, rama `feat/paso-NN`, un commit por entrada cuando
tenga sentido, tests + Postman + E2E actualizados en el mismo paso con la CI en verde, PR revisada
y mergeada por el usuario.

## Pasos

| Paso | Contenido | Entradas | Llamadas reales |
|------|-----------|----------|-----------------|
| 17. Modelo de datos v2 y migración | Quitar campos del proyecto (contenido → Descripción), un solo tipo de imagen, sin estados de rechazo/descarte, selección única por etapa, sin recomposición ni salida en bruto; migración automática con copia de los originales | B-026, B-028 (datos), B-048, B-043 (selección), B-038 (datos) | No |
| 18. Configuración de los modelos de IA | Rol `REFERENCE_ANALYST`, esfuerzo de razonamiento por rol en `.env` (`medium`), fidelidad alta en sunburst, semilla y proporciones en FLUX, especialización en el código | B-052 (roles), B-053, B-041, B-037 (base) | Verificación (≈ 0,10 €) |
| 19. Proyectos y cabecera | Nombre y descripción; último proyecto por defecto; desglose de costes con todas las llamadas; miniatura más avanzada; orden de la cabecera | B-025, B-026 (interfaz), B-027, B-044, B-050 | No |
| 20. Costes IA | Pestaña renombrada y solo gasto real; leyendas y ejes; registro de llamadas con «ver más»; precios alineados con unidades | B-031 a B-034 | No |
| 21. Referencias v2 | Pestaña «Referencias» sin tipos; indexación automática al subir (Notas, receta JSON); ficha de casillas con «Guardar ficha»; prompt de recetas; prueba comparativa luna/sol; reindexado de las referencias existentes | B-028 (interfaz), B-029, B-030, B-054, B-052 | ≈ 0,10-0,20 € |
| 22. Estudio I: base común y Bocetos | Tres pestañas con desbloqueo progresivo; vista grande en proporción original con prompt y miniaturas del input; confirmación junto al botón; maquetación 50/50; Bocetos con brief automático (luna), variantes 1-8, calidad media, umbral 0,15 € | B-035, B-036, B-040, B-042, B-043, B-047, B-049, B-054 | ≈ 0,15-0,30 € |
| 23. Estudio II: Composición | Auditoría opcional del boceto (astra); retoques con máscara solo sobre la composición seleccionada y sin recomposición; crear composición desde el boceto o la composición seleccionada; editor de máscaras sin paleta | B-045, B-046, B-038, B-039, B-040, B-054 | ≈ 0,30-0,50 € |
| 24. Estudio III: Render Final | FLUX con texto libre sobre la composición o el render seleccionado; proporción y resolución (máxima por defecto); «Otra versión» con el prompt bloqueado (la semilla de Azure no es reproducible) | B-051, B-040, B-037, B-054 | ≈ 0,15-0,30 € |
| 25. Versión 2.0.0 | README de la v2 (las capturas, B-023, quedan para la siguiente versión menor); Gradio y Pillow 13 revisados (B-024 sigue abierto); documentación, CHANGELOG, etiqueta y Release | B-023, B-024 | No |

Gasto real estimado del plan: ≈ 1-1,5 € (cada llamada se anuncia antes).

## Decisiones de enfoque (aprobadas)

1. La API sigue siendo `/api/v1`, con los cambios incompatibles documentados: el frontend es su
   único cliente.
2. Los briefs antiguos se conservan en los datos como historia, pero la interfaz nueva no los
   muestra; los bocetos, composiciones y renders existentes siguen visibles.

## Lo que aporta el usuario

- Paso 21: decidir con la comparativa luna/sol.
- Pasos 21 a 24: confirmar las llamadas reales anunciadas.
- Pasos 22 en adelante: trabajar juntos los prompts de sistema (B-054).
- Antes del Paso 25: el caso de uso de demostración para las capturas.
