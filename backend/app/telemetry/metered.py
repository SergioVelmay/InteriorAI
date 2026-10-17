"""`MeteredFoundryClient`: envuelve cualquier `FoundryClient` y registra cada llamada.

Mide latencia (incluidos reintentos), tokens, imágenes y megapíxeles, estima el coste con
`pricing.yaml` y lo guarda en el proyecto del `telemetry_scope` activo. Las llamadas fallidas
también se registran (con su coste si el proveedor informó del uso).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from io import BytesIO
from typing import Protocol, TypeVar
from uuid import UUID

from PIL import Image, UnidentifiedImageError

from app.foundry.base import FoundryClient
from app.foundry.errors import FoundryError
from app.foundry.types import (
    ImageEditRequest,
    ImageRequest,
    ImageResult,
    TextRequest,
    TextResult,
    Usage,
)
from app.telemetry.context import current_project_id, current_request_id
from app.telemetry.pricing import PricingTable, estimate_cost, megapixels
from shared.models import AiOperation, TelemetryRecord
from shared.roles import Role

logger = logging.getLogger("interiorai.telemetry")

R = TypeVar("R", TextResult, ImageResult)


class TelemetrySink(Protocol):
    async def append_telemetry(self, project_id: UUID, record: TelemetryRecord) -> None: ...


class MeteredFoundryClient(FoundryClient):
    def __init__(
        self,
        inner: FoundryClient,
        pricing: PricingTable | None,
        sink: TelemetrySink,
        deployment_for: Callable[[Role], str],
        simulated: bool,
    ) -> None:
        self.inner = inner
        self.pricing = pricing
        self._sink = sink
        self._deployment_for = deployment_for
        self._simulated = simulated

    async def aclose(self) -> None:
        await self.inner.aclose()

    async def _complete_text(self, role: Role, request: TextRequest) -> TextResult:
        return await self._measure(
            role, "complete_text", lambda: self.inner.complete_text(role, request), []
        )

    async def _generate_image(self, role: Role, request: ImageRequest) -> ImageResult:
        return await self._measure(
            role, "generate_image", lambda: self.inner.generate_image(role, request), []
        )

    async def _edit_image(self, role: Role, request: ImageEditRequest) -> ImageResult:
        references = [_size_of(img.data) for img in request.images]
        return await self._measure(
            role, "edit_image", lambda: self.inner.edit_image(role, request), references
        )

    async def _measure(
        self,
        role: Role,
        operation: AiOperation,
        call: Callable[[], Awaitable[R]],
        references: list[tuple[int, int]],
    ) -> R:
        start = time.perf_counter()
        try:
            result = await call()
        except FoundryError as exc:
            await self._record(
                role, operation, time.perf_counter() - start, exc.usage or Usage(), [],
                references, error=exc,
            )  # fmt: skip
            raise
        images = (
            [(img.width, img.height) for img in result.images]
            if isinstance(result, ImageResult)
            else []
        )
        await self._record(
            role, operation, time.perf_counter() - start, result.usage, images, references
        )
        return result

    async def _record(
        self,
        role: Role,
        operation: AiOperation,
        latency_s: float,
        usage: Usage,
        images_out: list[tuple[int, int]],
        references: list[tuple[int, int]],
        error: FoundryError | None = None,
    ) -> None:
        deployment = self._deployment_for(role)
        cost = estimate_cost(self.pricing, deployment, usage, images_out, references)
        record = TelemetryRecord(
            request_id=current_request_id(),
            role=role,
            deployment=deployment,
            operation=operation,
            status="error" if error else "ok",
            error_type=type(error).__name__ if error else None,
            latency_s=round(latency_s, 3),
            input_tokens=usage.input_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            input_text_tokens=usage.input_text_tokens,
            input_image_tokens=usage.input_image_tokens,
            output_tokens=usage.output_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            images_out=len(images_out),
            megapixels_out=round(sum(megapixels(w, h) for w, h in images_out), 6),
            megapixels_ref=round(sum(megapixels(w, h) for w, h in references), 6),
            cost_eur=cost.total if cost else None,
            cost_breakdown=cost.parts if cost else {},
            pricing_tier=cost.tier if cost else None,
            simulated=self._simulated,
        )
        logger.info(
            "Telemetría %s %s: %s | coste %s",
            role.value,
            operation,
            record.status,
            f"{record.cost_eur:.6f} EUR" if record.cost_eur is not None else "sin precio",
        )
        project_id = current_project_id()
        if project_id is None:
            return
        try:
            await self._sink.append_telemetry(project_id, record)
        except Exception:  # la telemetría nunca debe romper la llamada a la IA
            logger.exception("No se pudo guardar la telemetría del proyecto %s", project_id)


def _size_of(data: bytes) -> tuple[int, int]:
    try:
        with Image.open(BytesIO(data)) as image:
            return image.size
    except (UnidentifiedImageError, OSError):
        return (0, 0)
