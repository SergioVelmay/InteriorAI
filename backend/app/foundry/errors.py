"""Errores del cliente de IA, independientes del proveedor."""

from __future__ import annotations

from app.foundry.types import Usage
from shared.roles import Role


class FoundryError(Exception):
    """Error al llamar a un despliegue. `usage` se rellena si la llamada se facturó igualmente."""

    def __init__(
        self,
        message: str,
        *,
        role: Role | None = None,
        status_code: int | None = None,
        usage: Usage | None = None,
    ) -> None:
        super().__init__(message)
        self.role = role
        self.status_code = status_code
        self.usage = usage


class FoundryAuthError(FoundryError):
    """Credenciales inválidas o sin permisos sobre el despliegue (401/403)."""


class FoundryRateLimitError(FoundryError):
    """Cuota agotada tras los reintentos (429)."""


class FoundryTimeoutError(FoundryError):
    pass


class FoundryContentFilterError(FoundryError):
    """El filtro de contenido de Azure bloqueó la petición o la respuesta."""


class FoundryBadRequestError(FoundryError):
    """Petición rechazada por el despliegue (400), p. ej. parámetro no admitido."""


class FoundryIncompleteError(FoundryError):
    """Respuesta incompleta (p. ej. se agotó `max_output_tokens`); se facturó igualmente."""


class FoundryUnsupportedError(FoundryError):
    """Operación no disponible para el rol o el proveedor (no llega a llamarse)."""
