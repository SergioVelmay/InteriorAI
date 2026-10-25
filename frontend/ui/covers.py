"""Portadas de los proyectos, leídas directamente del volumen compartido (solo lectura).

Lo más avanzado que exista (B-044): render final seleccionado → último render final →
composición seleccionada → última composición → boceto seleccionado → primer boceto → primera
referencia → imagen de relleno (proyecto sin imágenes).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from shared.models import (
    Asset,
    AssetKind,
    ProjectMetadata,
    RenderRecord,
    RenderStage,
    RenderStatus,
)

IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
PLACEHOLDER_SIZE = (960, 640)


def asset_path(data_dir: Path, project_id: object, asset: Asset) -> Path:
    return data_dir / str(project_id) / asset.kind.folder / asset.stored_name


def _candidates(project: ProjectMetadata) -> list[RenderRecord]:
    """Renders por preferencia: por etapa (la más avanzada primero), el seleccionado y luego
    el último; en los bocetos, el primero (el de la vista de partida del lote inicial)."""
    ordered: list[RenderRecord] = []
    for stage in (RenderStage.FINAL, RenderStage.COMPOSITION, RenderStage.DRAFT):
        renders = sorted(
            (r for r in project.renders if r.stage is stage), key=lambda r: r.created_at
        )
        ordered += [r for r in renders if r.status is RenderStatus.SELECTED]
        ordered += renders if stage is RenderStage.DRAFT else renders[::-1]
    return ordered


def cover_asset(project: ProjectMetadata) -> Asset | None:
    assets = {a.id: a for a in project.assets}
    for render in _candidates(project):
        if render.id in assets:
            return assets[render.id]
    references = sorted(
        (a for a in project.assets if a.kind is AssetKind.REFERENCIA), key=lambda a: a.created_at
    )
    return next((a for a in references if a.mime_type in IMAGE_TYPES), None)


def placeholder(name: str) -> Image.Image:
    """Imagen de relleno oscura con la inicial del proyecto (color estable por nombre)."""
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    tint = (24 + digest[0] % 24, 24 + digest[1] % 24, 30 + digest[2] % 30)
    image = Image.new("RGB", PLACEHOLDER_SIZE, (17, 17, 19))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, *PLACEHOLDER_SIZE), fill=tint)
    font = ImageFont.load_default(size=220)
    initial = (name.strip()[:1] or "?").upper()
    box = draw.textbbox((0, 0), initial, font=font)
    x = (PLACEHOLDER_SIZE[0] - (box[2] - box[0])) // 2 - box[0]
    y = (PLACEHOLDER_SIZE[1] - (box[3] - box[1])) // 2 - box[1]
    draw.text((x, y), initial, fill=(161, 161, 170), font=font)
    return image


def cover_image(project: ProjectMetadata, data_dir: Path) -> str | Image.Image:
    """Ruta de la portada en el volumen o, si no hay o no existe, imagen de relleno."""
    asset = cover_asset(project)
    if asset is not None:
        path = asset_path(data_dir, project.id, asset)
        if path.is_file():
            return str(path)
    return placeholder(project.name)
