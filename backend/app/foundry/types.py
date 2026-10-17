"""Peticiones y resultados del cliente de IA, independientes del proveedor.

Cada resultado incluye lo necesario para la telemetría de costes (Paso 7): rol, despliegue,
latencia y uso de tokens.
"""

from __future__ import annotations

import base64
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.roles import Role

_SIZE = re.compile(r"^(\d{2,5})x(\d{2,5})$")


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Usage(_Model):
    """Tokens de una llamada. Los desgloses son subconjuntos de `input_tokens`/`output_tokens`."""

    input_tokens: int = 0
    cached_input_tokens: int = 0  # entrada servida desde caché (texto)
    cache_write_tokens: int = 0  # entrada escrita en caché (texto)
    input_text_tokens: int = 0  # imágenes por tokens: parte textual de la entrada
    input_image_tokens: int = 0  # imágenes por tokens: imágenes de entrada (ediciones)
    output_tokens: int = 0
    reasoning_tokens: int = 0  # ya incluidos en output_tokens (serie GPT-6 / Responses API)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class InputImage(_Model):
    data: bytes = Field(repr=False)
    mime_type: str = "image/png"

    def data_url(self) -> str:
        return f"data:{self.mime_type};base64,{base64.b64encode(self.data).decode()}"


class TextRequest(_Model):
    input: str = Field(min_length=1)
    instructions: str = ""
    images: list[InputImage] = Field(default_factory=list)
    # JSON Schema estricto (todas las propiedades en `required`, `additionalProperties: false`)
    json_schema: dict[str, Any] | None = None
    schema_name: str = Field(default="respuesta", pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    max_output_tokens: int | None = Field(default=None, gt=0)


class TextResult(_Model):
    role: Role
    deployment: str
    text: str
    data: dict[str, Any] | None = None  # JSON parseado si se pidió `json_schema`
    usage: Usage
    latency_s: float
    response_id: str | None = None


class ImageRequest(_Model):
    prompt: str = Field(min_length=1)
    size: str = "1024x1024"
    n: int = Field(default=1, ge=1, le=4)
    quality: Literal["low", "medium", "high", "auto"] = "auto"
    output_format: Literal["png", "jpeg"] = "png"
    seed: int | None = None  # solo renderizador

    @field_validator("size")
    @classmethod
    def _valid_size(cls, value: str) -> str:
        if not _SIZE.fullmatch(value):
            raise ValueError("size debe tener el formato <ancho>x<alto>, p. ej. 1024x1024")
        return value

    @property
    def width(self) -> int:
        return int(self.size.split("x")[0])

    @property
    def height(self) -> int:
        return int(self.size.split("x")[1])


class ImageEditRequest(ImageRequest):
    images: list[InputImage] = Field(min_length=1, max_length=8)
    # Máscara RGBA: las zonas transparentes son las que se regeneran (inpainting).
    mask: InputImage | None = None


class GeneratedImage(_Model):
    data: bytes = Field(repr=False)
    mime_type: str
    width: int
    height: int


class ImageResult(_Model):
    role: Role
    deployment: str
    images: list[GeneratedImage]
    usage: Usage
    latency_s: float
