"""Máscaras de retoque (inpainting) y ajuste de tamaño de las imágenes generadas.

Convención de la API: la máscara es una imagen con la misma proporción que la retocada; la
**zona a editar** son los píxeles pintados (opacos si la imagen tiene transparencia, claros si
no). El modelo recibe la máscara nativa y su imagen se guarda completa (B-038: sin recomponer).
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

from app.pipelines.errors import PipelineInputError

ASPECT_TOLERANCE = 0.02
MAX_COVERAGE = 0.9  # por encima, mejor generar una imagen nueva entera


def _open(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PipelineInputError("La máscara no es una imagen válida") from exc
    return image


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def edit_zone(mask_data: bytes, size: tuple[int, int]) -> Image.Image:
    """Máscara del usuario → imagen `L` del tamaño `size` (255 = editar, 0 = conservar)."""
    mask = _open(mask_data)
    width, height = size
    if abs(mask.width / mask.height - width / height) > ASPECT_TOLERANCE * width / height:
        raise PipelineInputError(
            f"La máscara ({mask.width}x{mask.height}) no tiene la proporción de la imagen "
            f"({width}x{height})"
        )
    if mask.mode in {"RGBA", "LA", "PA"} or (mask.mode == "P" and "transparency" in mask.info):
        channel = mask.convert("RGBA").getchannel("A")
    else:
        channel = mask.convert("L")
    zone = channel.point(lambda v: 255 if v >= 128 else 0)
    if zone.size != size:
        zone = zone.resize(size, Image.Resampling.NEAREST)
    return zone


def coverage(zone: Image.Image) -> float:
    histogram = zone.histogram()
    return histogram[255] / (zone.width * zone.height)


def check_coverage(zone: Image.Image) -> float:
    value = coverage(zone)
    if value == 0:
        raise PipelineInputError("La máscara está vacía: pinta la zona que quieres cambiar")
    if value > MAX_COVERAGE:
        raise PipelineInputError(
            "La máscara cubre casi toda la imagen: para eso, genera una composición nueva"
        )
    return round(value, 4)


def model_mask(zone: Image.Image, size: tuple[int, int]) -> bytes:
    """Máscara para la API de edición con máscara: RGBA, transparente = zona a regenerar."""
    resized = zone.resize(size, Image.Resampling.NEAREST)
    mask = Image.new("RGBA", size, (0, 0, 0, 255))
    mask.putalpha(resized.point(lambda v: 0 if v else 255))
    return _png(mask)


def fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Ajusta sin deformar: recorta al centro hasta la proporción de `size` y escala si hace
    falta. Con 1920x1088 → 1920x1080 solo recorta 4 px arriba y 4 abajo (sin escalar)."""
    if image.size == size:
        return image
    width, height = image.size
    target = size[0] / size[1]
    if width / height > target:  # sobra ancho
        new_width = round(height * target)
        left = (width - new_width) // 2
        image = image.crop((left, 0, left + new_width, height))
    elif width / height < target:  # sobra alto
        new_height = round(width / target)
        top = (height - new_height) // 2
        image = image.crop((0, top, width, top + new_height))
    if image.size != size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    return image


def fit_png(data: bytes, size: tuple[int, int]) -> bytes:
    image = _open(data)
    if image.size == size:
        return data
    return _png(fit(image.convert("RGB"), size))


def zone_png(zone: Image.Image) -> bytes:
    """Máscara normalizada que se guarda con el retoque (blanco = zona editada)."""
    return _png(zone)


def zone_bounds_text(zone: Image.Image) -> str:
    """Posición de la zona en porcentajes (desde la esquina superior izquierda) para el prompt:
    refuerza en texto la zona de la máscara."""
    left, top, right, bottom = zone.getbbox() or (0, 0, zone.width, zone.height)
    return (
        f"horizontally from {100 * left / zone.width:.0f}% to {100 * right / zone.width:.0f}% "
        f"of the width and vertically from {100 * top / zone.height:.0f}% to "
        f"{100 * bottom / zone.height:.0f}% of the height, measured from the top-left corner"
    )
