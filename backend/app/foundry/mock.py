"""Cliente simulado (`AI_PROVIDER_MODE=mock`): determinista, sin red y sin coste.

- Texto: respuesta fija que identifica el rol; si se pide `json_schema`, un JSON válido.
- Imágenes: PNG con degradado derivado del prompt y la etiqueta «MOCK · ROL · WxH».
- Uso: tokens simulados (≈ caracteres / 4) para poder probar la telemetría de costes.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import math
import time
from typing import Any

import anyio
from PIL import Image, ImageDraw, ImageFont

from app.foundry.base import FoundryClient, log_call
from app.foundry.types import (
    GeneratedImage,
    ImageEditRequest,
    ImageRequest,
    ImageResult,
    TextRequest,
    TextResult,
    Usage,
)
from shared.roles import ApiKind, Role

IMAGE_INPUT_TOKENS = 85  # coste simulado de cada imagen de entrada


def _tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def sample_from_schema(schema: dict[str, Any]) -> Any:
    """Valor mínimo que cumple un JSON Schema sencillo (sin `$ref`)."""
    for key in ("anyOf", "oneOf"):
        if key in schema:
            return sample_from_schema(schema[key][0])
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type", "object")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "null")
    if kind == "object":
        properties = schema.get("properties", {})
        return {name: sample_from_schema(sub) for name, sub in properties.items()}
    if kind == "array":
        return [sample_from_schema(schema.get("items", {"type": "string"}))]
    if kind == "string":
        return "mock"
    if kind == "integer":
        return int(schema.get("minimum", 0))
    if kind == "number":
        return float(schema.get("minimum", 0))
    if kind == "boolean":
        return True
    return None


def _palette(seed: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return (digest[0], digest[1], digest[2]), (digest[3], digest[4], digest[5])


def _label(image: Image.Image, text: str) -> None:
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(14, image.width // 32))
    box = draw.textbbox((0, 0), text, font=font)
    x = (image.width - (box[2] - box[0])) // 2
    y = (image.height - (box[3] - box[1])) // 2
    pad = image.width // 64
    draw.rectangle(
        (x - pad, y - pad, x + box[2] - box[0] + pad, y + box[3] - box[1] + pad), fill=(10, 10, 10)
    )
    draw.text((x, y), text, fill=(250, 250, 250), font=font)


def _gradient(width: int, height: int, seed: str) -> Image.Image:
    (r1, g1, b1), (r2, g2, b2) = _palette(seed)
    top = Image.new("RGB", (width, height), (r1, g1, b1))
    bottom = Image.new("RGB", (width, height), (r2, g2, b2))
    ramp = Image.linear_gradient("L").resize((width, height))
    return Image.composite(bottom, top, ramp)


def _encode(image: Image.Image, output_format: str) -> GeneratedImage:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG" if output_format == "jpeg" else "PNG")
    return GeneratedImage(
        data=buffer.getvalue(),
        mime_type=f"image/{output_format}",
        width=image.width,
        height=image.height,
    )


def _render_generation(role: Role, request: ImageRequest, index: int) -> GeneratedImage:
    image = _gradient(request.width, request.height, f"{request.prompt}#{index}")
    _label(image, f"MOCK · {role.value} · {request.size}")
    return _encode(image, request.output_format)


def _render_edit(role: Role, request: ImageEditRequest, index: int) -> GeneratedImage:
    size = (request.width, request.height)
    base = Image.open(io.BytesIO(request.images[0].data)).convert("RGB").resize(size)
    tint = _gradient(*size, f"{request.prompt}#{index}")
    if request.mask is not None:
        # Zonas transparentes de la máscara = zona editada: se rellenan con el degradado.
        alpha = Image.open(io.BytesIO(request.mask.data)).convert("RGBA").resize(size)
        edit_zone = alpha.getchannel("A").point(lambda a: 255 if a < 128 else 0)
        image = Image.composite(tint, base, edit_zone)
    else:
        image = Image.blend(base, tint, 0.35)
    _label(image, f"MOCK EDIT · {role.value} · {request.size}")
    return _encode(image, request.output_format)


def _image_usage(role: Role, prompt: str, width: int, height: int, n: int, inputs: int) -> Usage:
    if role.api_kind is ApiKind.PROVIDER_IMAGES:
        return Usage()  # el renderizador se factura por imagen, no por tokens
    text_tokens, image_tokens = _tokens(prompt), inputs * IMAGE_INPUT_TOKENS
    return Usage(
        input_tokens=text_tokens + image_tokens,
        input_text_tokens=text_tokens,
        input_image_tokens=image_tokens,
        output_tokens=n * (width * height) // 4096,
    )


class MockFoundryClient(FoundryClient):
    def __init__(self, latency_s: float = 0.0) -> None:
        self.latency_s = latency_s

    async def _simulate_latency(self) -> None:
        if self.latency_s:
            await asyncio.sleep(self.latency_s)

    async def _complete_text(self, role: Role, request: TextRequest) -> TextResult:
        start = time.perf_counter()
        await self._simulate_latency()
        data = sample_from_schema(request.json_schema) if request.json_schema else None
        if data is not None:
            text = json.dumps(data, ensure_ascii=False)
        else:
            preview = " ".join(request.input.split())[:120]
            text = f"[MOCK {role.value}] Respuesta simulada para: {preview}"
        output = _tokens(text)
        usage = Usage(
            input_tokens=_tokens(request.instructions + request.input)
            + len(request.images) * IMAGE_INPUT_TOKENS,
            output_tokens=output * 5 if role is Role.GEOMETRIC_AUDITOR else output,
            reasoning_tokens=output * 4 if role is Role.GEOMETRIC_AUDITOR else 0,
        )
        latency = time.perf_counter() - start
        deployment = f"mock-{role.value.lower()}"
        log_call(role, deployment, latency, usage, "mock")
        return TextResult(
            role=role,
            deployment=deployment,
            text=text,
            data=data,
            usage=usage,
            latency_s=latency,
            response_id=f"mock-{hashlib.sha256(text.encode()).hexdigest()[:12]}",
        )

    async def _images(self, role: Role, render, request: ImageRequest, inputs: int) -> ImageResult:
        start = time.perf_counter()
        await self._simulate_latency()
        images = [
            await anyio.to_thread.run_sync(render, role, request, i) for i in range(request.n)
        ]
        usage = _image_usage(role, request.prompt, request.width, request.height, request.n, inputs)
        latency = time.perf_counter() - start
        deployment = f"mock-{role.value.lower()}"
        log_call(role, deployment, latency, usage, f"mock · {request.n} imagen(es) {request.size}")
        return ImageResult(
            role=role, deployment=deployment, images=images, usage=usage, latency_s=latency
        )

    async def _generate_image(self, role: Role, request: ImageRequest) -> ImageResult:
        return await self._images(role, _render_generation, request, inputs=0)

    async def _edit_image(self, role: Role, request: ImageEditRequest) -> ImageResult:
        return await self._images(role, _render_edit, request, inputs=len(request.images))
