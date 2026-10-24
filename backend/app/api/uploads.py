"""Validación de subidas: tamaño, Base64, tipo real del archivo e integridad de imágenes.

Nunca se confía en la extensión ni en el `Content-Type` del cliente: el tipo se detecta
por la firma (magic bytes) y las imágenes se decodifican por completo con Pillow.
"""

from __future__ import annotations

import base64
import binascii
import re
import warnings
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO

import anyio
from fastapi import UploadFile, status
from PIL import Image, UnidentifiedImageError

from shared.models import AssetKind

PNG, JPEG, WEBP, PDF = "image/png", "image/jpeg", "image/webp", "application/pdf"
IMAGE_TYPES = frozenset({PNG, JPEG, WEBP})

# Límite de píxeles (protección contra "bombas de descompresión"): 80 MP cubre renders 8K.
MAX_IMAGE_PIXELS = 80_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
# Pillow solo avisa entre 1x y 2x el límite: se convierte en error para rechazar siempre.
warnings.simplefilter("error", Image.DecompressionBombWarning)

_PIL_FORMATS = {PNG: "PNG", JPEG: "JPEG", WEBP: "WEBP"}
_DATA_URL = re.compile(r"^data:[\w.+-]+/[\w.+-]+;base64,", re.IGNORECASE)
_CHUNK = 1024 * 1024


class UploadKind(StrEnum):
    """Tipos de asset que el usuario puede subir: solo referencias (B-028). Los renders solo
    los genera la IA."""

    REFERENCIA = AssetKind.REFERENCIA.value

    @property
    def asset_kind(self) -> AssetKind:
        return AssetKind(self.value)


ACCEPTED_TYPES: dict[AssetKind, frozenset[str]] = {
    AssetKind.REFERENCIA: IMAGE_TYPES,  # solo imágenes (Paso 12): un PDF no llega a los modelos
    AssetKind.RENDER: IMAGE_TYPES,
}


class UploadError(Exception):
    def __init__(self, status_code: int, detail: str, extra: dict[str, str] | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.extra = extra or {}


@dataclass(frozen=True)
class InspectedFile:
    mime_type: str
    width_px: int | None = None
    height_px: int | None = None


def _too_large(max_bytes: int) -> UploadError:
    return UploadError(
        status.HTTP_413_CONTENT_TOO_LARGE,
        f"El archivo supera el tamaño máximo de {max_bytes // (1024 * 1024)} MB",
    )


async def read_upload(file: UploadFile, max_bytes: int) -> bytes:
    """Lee un archivo multipart por bloques y corta en cuanto supera `max_bytes`."""
    buffer = bytearray()
    while chunk := await file.read(_CHUNK):
        buffer += chunk
        if len(buffer) > max_bytes:
            raise _too_large(max_bytes)
    if not buffer:
        raise UploadError(status.HTTP_422_UNPROCESSABLE_CONTENT, "El archivo está vacío")
    return bytes(buffer)


def decode_base64(data: str, max_bytes: int) -> bytes:
    """Decodifica Base64 (admite prefijo `data:<mime>;base64,`) validando antes el tamaño."""
    payload = "".join(_DATA_URL.sub("", data.strip(), count=1).split())
    estimated = len(payload) * 3 // 4 - payload[-2:].count("=")
    if estimated > max_bytes:
        raise _too_large(max_bytes)
    try:
        content = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise UploadError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "El contenido no es Base64 válido"
        ) from exc
    if not content:
        raise UploadError(status.HTTP_422_UNPROCESSABLE_CONTENT, "El archivo está vacío")
    return content


def detect_mime(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if content.startswith(b"\xff\xd8\xff"):
        return JPEG
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return WEBP
    if content.startswith(b"%PDF-"):
        return PDF
    return None


def _inspect_image(content: bytes, mime_type: str) -> tuple[int, int]:
    unsupported = UploadError(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "La imagen está dañada o no es válida"
    )
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format != _PIL_FORMATS[mime_type]:
                raise unsupported
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise UploadError(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    f"La imagen tiene demasiados píxeles ({width}x{height}); "
                    f"máximo {MAX_IMAGE_PIXELS // 1_000_000} MP",
                )
            image.load()  # decodificación completa: detecta archivos truncados o corruptos
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise UploadError(
            status.HTTP_413_CONTENT_TOO_LARGE, "La imagen tiene demasiados píxeles"
        ) from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise unsupported from exc
    return width, height


async def inspect_upload(content: bytes, kind: AssetKind) -> InspectedFile:
    """Valida el tipo real del archivo para `kind` y, si es imagen, su integridad."""
    accepted = ACCEPTED_TYPES[kind]
    mime_type = detect_mime(content)
    if mime_type not in accepted:
        formats = ", ".join(sorted(t.split("/")[1].upper() for t in accepted))
        raise UploadError(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Formato no admitido para '{kind.label}'. Formatos aceptados: {formats}",
        )
    if mime_type not in IMAGE_TYPES:
        return InspectedFile(mime_type)
    width, height = await anyio.to_thread.run_sync(_inspect_image, content, mime_type)
    return InspectedFile(mime_type, width, height)
