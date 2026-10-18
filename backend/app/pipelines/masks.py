"""Máscaras de retoque (inpainting) y recomposición local exacta (B-009).

Convención de la API: la máscara es una imagen con la misma proporción que la retocada; la
**zona a editar** son los píxeles pintados (opacos si la imagen tiene transparencia, claros si
no). Tras la llamada al modelo solo se aprovecha esa zona: el resto queda idéntico píxel a píxel.
"""

from __future__ import annotations

import io

from PIL import Image, ImageChops, ImageFilter, UnidentifiedImageError

from app.pipelines.errors import PipelineInputError

FEATHER_PX = 12  # suavizado del borde al recomponer (hacia fuera de la zona, hasta ~2x)
ASPECT_TOLERANCE = 0.02
MAX_COVERAGE = 0.9  # por encima, mejor rechazar y regenerar la imagen entera
GUIDE_MAX_SIDE = 1024  # imagen guía del renderizador (≈ 0,7 MP: cada MP de referencia cuesta)
GUIDE_COLOR = (255, 0, 0)


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
            "La máscara cubre casi toda la imagen: para eso, rechaza y regenera la imagen"
        )
    return round(value, 4)


def model_mask(zone: Image.Image, size: tuple[int, int]) -> bytes:
    """Máscara para la API de edición con máscara: RGBA, transparente = zona a regenerar."""
    resized = zone.resize(size, Image.Resampling.NEAREST)
    mask = Image.new("RGBA", size, (0, 0, 0, 255))
    mask.putalpha(resized.point(lambda v: 0 if v else 255))
    return _png(mask)


def guide_image(source_data: bytes, zone: Image.Image) -> bytes:
    """Copia reducida de la imagen con la zona a editar resaltada en rojo (para el renderizador,
    que no admite máscara): indica dónde aplicar el cambio."""
    source = _open(source_data).convert("RGB")
    overlay = Image.new("RGB", source.size, GUIDE_COLOR)
    zone_full = zone.resize(source.size, Image.Resampling.NEAREST)
    guide = Image.composite(Image.blend(source, overlay, 0.45), source, zone_full)
    # Contorno de la zona para que se distinga aunque el color de fondo sea rojizo.
    edges = zone_full.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(5))
    guide.paste(GUIDE_COLOR, mask=edges)
    guide.thumbnail((GUIDE_MAX_SIDE, GUIDE_MAX_SIDE), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    guide.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


def blend_mask(zone: Image.Image, feather_px: int) -> Image.Image:
    """Zona ampliada y difuminada: lo pintado se sustituye entero y la transición queda fuera."""
    if feather_px <= 0:
        return zone
    grown = zone.filter(ImageFilter.MaxFilter(2 * (feather_px // 2) + 1))
    return ImageChops.lighter(grown.filter(ImageFilter.GaussianBlur(feather_px / 2)), zone)


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


def recompose(
    source_data: bytes, generated_data: bytes, zone: Image.Image, feather_px: int = FEATHER_PX
) -> bytes:
    """Pega en la imagen original solo la zona editada de la generada (PNG, tamaño original)."""
    source = _open(source_data).convert("RGB")
    generated = fit(_open(generated_data).convert("RGB"), source.size)
    mask = blend_mask(zone.resize(source.size, Image.Resampling.NEAREST), feather_px)
    return _png(Image.composite(generated, source, mask))


def zone_png(zone: Image.Image) -> bytes:
    """Máscara normalizada que se guarda con el retoque (blanco = zona editada)."""
    return _png(zone)


def zone_bounds_text(zone: Image.Image) -> str:
    """Posición de la zona en porcentajes (desde la esquina superior izquierda) para el prompt:
    los modelos sin máscara la siguen mejor descrita en texto que solo coloreada."""
    left, top, right, bottom = zone.getbbox() or (0, 0, zone.width, zone.height)
    return (
        f"horizontally from {100 * left / zone.width:.0f}% to {100 * right / zone.width:.0f}% "
        f"of the width and vertically from {100 * top / zone.height:.0f}% to "
        f"{100 * bottom / zone.height:.0f}% of the height, measured from the top-left corner"
    )
