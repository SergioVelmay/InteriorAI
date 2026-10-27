"""Uso de las referencias en el diseño.

Desde la v2 toda imagen subida es una referencia (B-028) con su ficha (B-030). Solo cuentan las
**activas** (ficha con algún elemento marcado). Las reglas de lo que recibe cada generación están
en `shared.supports` (Paso 23), compartidas con la interfaz:

- Imagen base de los bocetos: la primera referencia activa con algo marcado en «Perspectiva y
  punto de vista»; sin ninguna, el modelo compone libremente.
- Apoyos de bocetos, composiciones y retoques: hasta `MAX_SUPPORTS` referencias activas, primero
  las del espacio (perspectiva, geometría) y después por antigüedad.
- Auditoría del boceto: todas las referencias activas con perspectiva o geometría marcadas.
- Render final: no recibe referencias; lo marcado en las fichas llega como texto al prompt.
"""

from __future__ import annotations

from shared.supports import (  # reglas compartidas con la interfaz (Paso 23)
    MAX_SUPPORTS,
    SPACE_GROUPS,
    active_references,
    draft_base,
    geometric_references,
    prioritized_supports,
    split_supports,
    with_group,
)

__all__ = [
    "MAX_SUPPORTS",
    "SPACE_GROUPS",
    "active_references",
    "draft_base",
    "geometric_references",
    "prioritized_supports",
    "split_supports",
    "with_group",
]
