"""Interfaz común de los clientes de IA, accedidos únicamente por rol."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from app.foundry.errors import FoundryUnsupportedError
from app.foundry.types import (
    ImageEditRequest,
    ImageRequest,
    ImageResult,
    TextRequest,
    TextResult,
    Usage,
)
from shared.roles import ApiKind, Role

logger = logging.getLogger("interiorai.foundry")

_TEXT_KINDS = frozenset({ApiKind.RESPONSES})
_IMAGE_KINDS = frozenset({ApiKind.IMAGES, ApiKind.PROVIDER_IMAGES})


def _require(role: Role, kinds: frozenset[ApiKind], operation: str) -> None:
    if role.api_kind not in kinds:
        raise FoundryUnsupportedError(
            f"El rol {role.value} ({role.api_kind.value}) no admite '{operation}'", role=role
        )


def log_call(role: Role, deployment: str, latency_s: float, usage: Usage, extra: str = "") -> None:
    logger.info(
        "IA %s -> %s | %.2fs | tokens entrada/salida/razonamiento %d/%d/%d%s",
        role.value,
        deployment,
        latency_s,
        usage.input_tokens,
        usage.output_tokens,
        usage.reasoning_tokens,
        f" | {extra}" if extra else "",
    )


# Único rol con máscara (B-037): bocetos sin máscara y fotorrealismo sin retoques de zona.
MASK_ROLE = Role.COMPOSITION_BUILDER


class FoundryClient(ABC):
    """Valida rol y operación y delega en la implementación concreta."""

    async def complete_text(self, role: Role, request: TextRequest) -> TextResult:
        _require(role, _TEXT_KINDS, "complete_text")
        return await self._complete_text(role, request)

    async def generate_image(self, role: Role, request: ImageRequest) -> ImageResult:
        _require(role, _IMAGE_KINDS, "generate_image")
        return await self._generate_image(role, request)

    async def edit_image(self, role: Role, request: ImageEditRequest) -> ImageResult:
        _require(role, _IMAGE_KINDS, "edit_image")
        if request.mask is not None and role is not MASK_ROLE:
            raise FoundryUnsupportedError(
                f"El rol {role.value} no admite máscara (especialización de los modelos de "
                f"imagen, B-037); para retoques de una zona usa {MASK_ROLE.value}",
                role=role,
            )
        return await self._edit_image(role, request)

    async def aclose(self) -> None:  # noqa: B027 — opcional para implementaciones sin recursos
        """Libera conexiones."""

    @abstractmethod
    async def _complete_text(self, role: Role, request: TextRequest) -> TextResult: ...

    @abstractmethod
    async def _generate_image(self, role: Role, request: ImageRequest) -> ImageResult: ...

    @abstractmethod
    async def _edit_image(self, role: Role, request: ImageEditRequest) -> ImageResult: ...
