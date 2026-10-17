"""Acceso a la IA por rol funcional (Azure AI Foundry o simulación)."""

from app.foundry.base import FoundryClient
from app.foundry.errors import (
    FoundryAuthError,
    FoundryBadRequestError,
    FoundryContentFilterError,
    FoundryError,
    FoundryIncompleteError,
    FoundryRateLimitError,
    FoundryTimeoutError,
    FoundryUnsupportedError,
)
from app.foundry.mock import MockFoundryClient
from app.foundry.types import (
    GeneratedImage,
    ImageEditRequest,
    ImageRequest,
    ImageResult,
    InputImage,
    TextRequest,
    TextResult,
    Usage,
)
from shared import Settings


def create_foundry_client(settings: Settings) -> FoundryClient:
    if settings.is_mock:
        return MockFoundryClient()
    from app.foundry.azure import AzureFoundryClient

    return AzureFoundryClient(settings)


__all__ = [
    "FoundryAuthError",
    "FoundryBadRequestError",
    "FoundryClient",
    "FoundryContentFilterError",
    "FoundryError",
    "FoundryIncompleteError",
    "FoundryRateLimitError",
    "FoundryTimeoutError",
    "FoundryUnsupportedError",
    "GeneratedImage",
    "ImageEditRequest",
    "ImageRequest",
    "ImageResult",
    "InputImage",
    "MockFoundryClient",
    "TextRequest",
    "TextResult",
    "Usage",
    "create_foundry_client",
]
