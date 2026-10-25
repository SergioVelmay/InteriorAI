"""Uso de las referencias en el diseño mientras llega el Estudio nuevo (puente hasta el Paso 22).

Desde la v2 toda imagen subida es una referencia (B-028) con su ficha (B-030). Solo cuentan las
**activas** (ficha con algún elemento marcado). Reglas aprobadas en el Paso 21:

- Imagen base de bocetos, composiciones y auditoría: la primera referencia activa con algo
  marcado en «Perspectiva y punto de vista». Si no hay ninguna, la regla anterior: captura de
  SketchUp de la v1, plano de la v1 y, por último, la referencia en imagen más antigua.
- Imágenes que recibe el brief: las referencias activas con perspectiva o geometría marcadas
  (perspectiva primero); si no hay, como antes (capturas y planos de la v1, o la imagen base).
- Fichas que recibe el brief: lo marcado en las referencias activas.
- Texturas del render final: las referencias activas, salvo la imagen base.
"""

from __future__ import annotations

from app.pipelines.images import VISION_MIME_TYPES
from shared.models import Asset, AssetKind, ProjectMetadata

_LEGACY_ORDER = {"captura_sketchup": 0, "plano": 1}


def _by_age(assets: list[Asset]) -> list[Asset]:
    return sorted(assets, key=lambda a: a.created_at)


def _unique(assets: list[Asset]) -> list[Asset]:
    """Sin repetir (por id), conservando el orden."""
    seen: set = set()
    return [a for a in assets if not (a.id in seen or seen.add(a.id))]


def _images(assets: list[Asset]) -> list[Asset]:
    return [a for a in assets if a.mime_type in VISION_MIME_TYPES]


def active_references(project: ProjectMetadata) -> list[Asset]:
    """Referencias con ficha y algún elemento marcado, de la más antigua a la más reciente."""
    return _by_age(
        [
            a
            for a in project.assets
            if a.kind is AssetKind.REFERENCIA and a.sheet is not None and a.sheet.active
        ]
    )


def with_group(project: ProjectMetadata, group: str) -> list[Asset]:
    """Referencias activas con algo marcado en `group` (p. ej. «perspectiva»)."""
    return [
        a
        for a in active_references(project)
        if any(element.startswith(f"{group}:") for element in a.sheet.selected)  # type: ignore[union-attr]
    ]


def legacy_sources(project: ProjectMetadata) -> list[Asset]:
    """Capturas y planos migrados de la v1: capturas primero y, dentro, por antigüedad."""
    return sorted(
        (a for a in project.assets if a.legacy_kind is not None),
        key=lambda a: (_LEGACY_ORDER[a.legacy_kind], a.created_at),  # type: ignore[index]
    )


def base_candidates(project: ProjectMetadata) -> list[Asset]:
    """Imágenes que pueden servir de base, por preferencia (solo formatos de visión)."""
    others = _by_age(
        [a for a in project.assets if a.kind is AssetKind.REFERENCIA and a.legacy_kind is None]
    )
    ordered = [*with_group(project, "perspectiva"), *legacy_sources(project), *others]
    return _images(_unique(ordered))


def brief_images(project: ProjectMetadata) -> list[Asset]:
    """Imágenes adjuntas al brief: las del espacio (perspectiva y geometría marcadas)."""
    space = _unique([*with_group(project, "perspectiva"), *with_group(project, "geometria")])
    if space:
        return _images(space)
    return _images(legacy_sources(project)) or base_candidates(project)[:1]


def texture_references(project: ProjectMetadata, base: Asset | None) -> list[Asset]:
    """Referencias del render final: las activas en imagen, salvo la imagen base."""
    return [a for a in _images(active_references(project)) if base is None or a.id != base.id]
