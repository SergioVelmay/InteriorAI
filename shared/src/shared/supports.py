"""Qué referencias recibe cada generación (Paso 23): reglas puras compartidas por el backend,
que las aplica, y la interfaz, que muestra de antemano qué se envía y qué queda fuera.

Solo cuentan las referencias **activas** (ficha con algún elemento marcado) en un formato de
imagen que admiten los modelos. Los modelos GPT de imagen reciben la imagen de partida y hasta
`MAX_SUPPORTS` apoyos: primero los del espacio (perspectiva, geometría) y después por
antigüedad; los que no caben quedan fuera (la interfaz los señala en rojo).
"""

from __future__ import annotations

from shared.models import Asset, AssetKind, ProjectMetadata

VISION_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
# Decisión del usuario (Paso 23): OpenAI documenta hasta 16 imágenes por edición.
MAX_SUPPORTS = 12
SPACE_GROUPS = ("perspectiva", "geometria")


def by_age(assets: list[Asset]) -> list[Asset]:
    return sorted(assets, key=lambda a: a.created_at)


def unique(assets: list[Asset]) -> list[Asset]:
    """Sin repetir (por id), conservando el orden."""
    seen: set = set()
    return [a for a in assets if not (a.id in seen or seen.add(a.id))]


def images(assets: list[Asset]) -> list[Asset]:
    return [a for a in assets if a.mime_type in VISION_MIME_TYPES]


def active_references(project: ProjectMetadata) -> list[Asset]:
    """Referencias con ficha y algún elemento marcado, de la más antigua a la más reciente."""
    return by_age(
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


def geometric_references(project: ProjectMetadata) -> list[Asset]:
    """Referencias activas con perspectiva o geometría marcadas (las del espacio), en imagen."""
    return images(unique([a for group in SPACE_GROUPS for a in with_group(project, group)]))


def draft_base(project: ProjectMetadata) -> Asset | None:
    """Imagen base de los bocetos: la primera referencia activa con perspectiva marcada."""
    return next(iter(images(with_group(project, "perspectiva"))), None)


def prioritized_supports(project: ProjectMetadata, start: Asset | None = None) -> list[Asset]:
    """Referencias activas en imagen por prioridad para enviarlas como apoyo: primero las del
    espacio y después por antigüedad; sin la imagen de partida."""
    ordered = unique([*geometric_references(project), *images(active_references(project))])
    return [a for a in ordered if start is None or a.id != start.id]


def split_supports(
    project: ProjectMetadata, start: Asset | None = None
) -> tuple[list[Asset], list[Asset]]:
    """(apoyos que se envían, los que quedan fuera por el tope de `MAX_SUPPORTS`)."""
    supports = prioritized_supports(project, start)
    return supports[:MAX_SUPPORTS], supports[MAX_SUPPORTS:]
