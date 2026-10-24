"""Imagen base del proyecto mientras llega el Estudio nuevo (puente hasta el Paso 22).

Desde la v2 toda imagen subida es una referencia (B-028). Las que en la v1 eran capturas de
SketchUp o planos conservan ese tipo en `legacy_kind` y siguen siendo, en este orden, la base
de los bocetos y composiciones, la geometría que recibe el brief y la referencia de la
auditoría. En un proyecto sin ellas, la base es la referencia en imagen más antigua.
"""

from __future__ import annotations

from app.pipelines.images import VISION_MIME_TYPES
from shared.models import Asset, AssetKind, ProjectMetadata

_LEGACY_ORDER = {"captura_sketchup": 0, "plano": 1}


def legacy_sources(project: ProjectMetadata) -> list[Asset]:
    """Capturas y planos migrados de la v1: capturas primero y, dentro, por antigüedad."""
    return sorted(
        (a for a in project.assets if a.legacy_kind is not None),
        key=lambda a: (_LEGACY_ORDER[a.legacy_kind], a.created_at),  # type: ignore[index]
    )


def base_candidates(project: ProjectMetadata) -> list[Asset]:
    """Imágenes que pueden servir de base, por preferencia (solo formatos de visión)."""
    others = sorted(
        (a for a in project.assets if a.kind is AssetKind.REFERENCIA and a.legacy_kind is None),
        key=lambda a: a.created_at,
    )
    return [a for a in [*legacy_sources(project), *others] if a.mime_type in VISION_MIME_TYPES]
