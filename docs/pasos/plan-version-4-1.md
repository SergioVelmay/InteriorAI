# Plan de acción — InteriorAI 4.1.0

Propuesto el 2026-11-02, tras publicar la 4.0.0, con lo que el usuario vio al usar la aplicación:
un proyecto que no aparecía al crear dos seguidos (B-107), la vista previa de la imagen al subir
una referencia (B-108), descartar candidatos de las galerías (B-109) y botones que se podían
volver a pulsar mientras la IA trabajaba (B-110).

## Por qué 4.1.0

Son funciones nuevas sin cambios incompatibles: la API gana los endpoints de descartar y
recuperar, y el estado de las imágenes, el valor «descartado». Según SemVer, una versión menor.
Los datos con descartes no los lee la 4.0.0 (como siempre al volver atrás).

## Pasos

| Paso | Contenido | Entradas | Llamadas reales |
|------|-----------|----------|-----------------|
| 41. Proyectos y referencias | Formulario de nuevo proyecto bloqueado mientras se crea; vista previa de la imagen al subir una referencia, «Cancelar», formulario bloqueado mientras sube y analiza, y borrado de las copias temporales | B-107, B-108 | No |
| 42. Botones bloqueados y apagados | Estilo «apagado» para todo botón desactivado; mientras se ve «procesando» en la pestaña, sus botones y miniaturas se apagan y no responden (pestañas y desplegables sí); con una confirmación abierta solo responden «Confirmar» y «Cancelar» | B-110 | No |
| 43. Descartes | Estado «descartado» con sus transiciones y endpoints; aspa en cada candidato salvo el seleccionado y «Descartar» junto a «Seleccionar»; desplegable «Descartados (n)» al final de cada pestaña, cerrado y solo con alguno, con ✓ para recuperar; la IA no ve los descartados; manual y capturas | B-109 | No |
| 44. Versión 4.1.0 | Versión, CHANGELOG, etiqueta y Release con el OK del usuario | — | No |

## Decisiones tomadas (usuario, 2026-11-02)

1. B-108: las «notas» del formulario de subir una referencia; con botón «Cancelar».
2. B-109: la IA no ve las imágenes descartadas entre las generaciones anteriores de la etapa.
3. B-109: el desplegable «Descartados» solo aparece si hay alguno.
4. B-109: capturas del manual actualizadas (copia local en simulación, sin coste).
5. B-110: mientras la IA trabaja se puede cambiar de pestaña y abrir o cerrar desplegables.
6. Versión 4.1.0 al terminar.
