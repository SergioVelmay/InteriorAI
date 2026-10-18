"""Preparación de imágenes para los modelos de texto con visión (control de tokens)."""

from __future__ import annotations

import io

import anyio
from PIL import Image

from app.foundry.types import InputImage

MAX_SIDE_PX = 1024
# Formatos que se pueden enviar a los modelos de visión (los PDF no)
VISION_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
JPEG_QUALITY = 85


def _prepare(data: bytes, max_side: int) -> bytes:
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        if image.mode in {"RGBA", "LA", "P"}:
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)  # nunca amplía
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return buffer.getvalue()


async def prepare_image(data: bytes, max_side: int = MAX_SIDE_PX) -> InputImage:
    """Reduce el lado largo a `max_side` y convierte a JPEG (transparencias sobre blanco)."""
    jpeg = await anyio.to_thread.run_sync(_prepare, data, max_side)
    return InputImage(data=jpeg, mime_type="image/jpeg")
