"""Uso de las referencias en el diseño.

Desde la v2 toda imagen subida es una referencia (B-028) con su ficha (B-030). Solo cuentan las
**activas** (ficha con algún elemento marcado). Las reglas de lo que recibe cada generación están
en `shared.supports` (Paso 23), compartidas con la interfaz:

- Imagen base de los bocetos: la primera referencia activa con algo marcado en «Perspectiva y
  punto de vista»; sin ninguna, el modelo compone libremente.
- Apoyos de bocetos, composiciones y retoques: hasta `MAX_SUPPORTS` referencias activas, primero
  las del espacio (perspectiva, geometría) y después por antigüedad.
- Auditoría del boceto: todas las referencias activas con perspectiva o geometría marcadas.
- Texturas del render final (provisional hasta el Paso 24): las activas, salvo la imagen base.

Cadenas de la v1 (con brief): imagen base según `base_candidates` (perspectiva, captura de
SketchUp, plano o la referencia más antigua) e imágenes del brief según `brief_images`.
"""

from __future__ import annotations

from shared.models import Asset, AssetKind, ProjectMetadata
from shared.supports import (  # reglas compartidas con la interfaz (Paso 23)
    MAX_SUPPORTS,
    SPACE_GROUPS,
    active_references,
    by_age,
    draft_base,
    geometric_references,
    images,
    prioritized_supports,
    split_supports,
    unique,
    with_group,
)

__all__ = [
    "MAX_SUPPORTS",
    "SPACE_GROUPS",
    "active_references",
    "base_candidates",
    "brief_images",
    "draft_base",
    "geometric_references",
    "legacy_sources",
    "prioritized_supports",
    "split_supports",
    "texture_references",
    "with_group",
]

_LEGACY_ORDER = {"captura_sketchup": 0, "plano": 1}


def legacy_sources(project: ProjectMetadata) -> list[Asset]:
    """Capturas y planos migrados de la v1: capturas primero y, dentro, por antigüedad."""
    return sorted(
        (a for a in project.assets if a.legacy_kind is not None),
        key=lambda a: (_LEGACY_ORDER[a.legacy_kind], a.created_at),  # type: ignore[index]
    )


def base_candidates(project: ProjectMetadata) -> list[Asset]:
    """Imágenes que pueden servir de base, por preferencia (solo formatos de visión)."""
    others = by_age(
        [a for a in project.assets if a.kind is AssetKind.REFERENCIA and a.legacy_kind is None]
    )
    ordered = [*with_group(project, "perspectiva"), *legacy_sources(project), *others]
    return images(unique(ordered))


def brief_images(project: ProjectMetadata) -> list[Asset]:
    """Imágenes adjuntas al brief: las del espacio (perspectiva y geometría marcadas)."""
    space = geometric_references(project)
    if space:
        return space
    return images(legacy_sources(project)) or base_candidates(project)[:1]


def texture_references(project: ProjectMetadata, base: Asset | None) -> list[Asset]:
    """Referencias del render final: las activas en imagen, salvo la imagen base."""
    return [a for a in images(active_references(project)) if base is None or a.id != base.id]
