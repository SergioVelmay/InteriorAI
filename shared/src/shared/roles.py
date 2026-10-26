"""Roles funcionales de IA.

El código solo conoce roles; el despliegue concreto de cada rol se resuelve desde
la configuración (`DEPLOYMENT_ROLE_<ROL>`). Aquí no aparece ningún nombre comercial.
"""

from enum import StrEnum
from typing import Any


class ApiKind(StrEnum):
    """Superficie de API de Azure AI Foundry que usa cada rol."""

    RESPONSES = "responses"  # /openai/v1/responses (texto, visión, razonamiento)
    IMAGES = "images"  # /openai/v1/images/{generations,edits}
    PROVIDER_IMAGES = "provider_images"  # /providers/<proveedor>/... (ruta propia)


class Role(StrEnum):
    PROMPT_ARCHITECT = "PROMPT_ARCHITECT"
    GEOMETRY_AUDITOR = "GEOMETRY_AUDITOR"
    REFERENCE_ANALYST = "REFERENCE_ANALYST"
    FAST_DRAFT_MAKER = "FAST_DRAFT_MAKER"
    COMPOSITION_BUILDER = "COMPOSITION_BUILDER"
    REALISTIC_RENDERER = "REALISTIC_RENDERER"

    @property
    def api_kind(self) -> ApiKind:
        return _API_KIND[self]

    @property
    def env_var(self) -> str:
        return f"DEPLOYMENT_ROLE_{self.value}"


# Nombres anteriores → actuales: CONTEXT_MANAGER en el Paso 18 y el resto en el Paso 26 (B-057,
# versión 3.0.0). Los datos guardados (telemetría y renders) se leen con el nombre actual sin
# reescribirse; en el `.env` solo valen los nombres actuales (`shared.settings.legacy_env_vars`).
RENAMED_ROLES: dict[str, Role] = {
    "CONTEXT_MANAGER": Role.REFERENCE_ANALYST,
    "PROMPT_ENGINEER": Role.PROMPT_ARCHITECT,
    "GEOMETRIC_AUDITOR": Role.GEOMETRY_AUDITOR,
    "FAST_DRAFT": Role.FAST_DRAFT_MAKER,
    "STRUCTURAL_COMPOSER": Role.COMPOSITION_BUILDER,
    "PHOTOREALISTIC_RENDERER": Role.REALISTIC_RENDERER,
}


def current_role(value: Any) -> Any:
    """Un rol guardado con su nombre anterior, con el actual (para validadores `before`)."""
    if isinstance(value, str) and value in RENAMED_ROLES:
        return RENAMED_ROLES[value].value
    return value


_API_KIND: dict[Role, ApiKind] = {
    Role.PROMPT_ARCHITECT: ApiKind.RESPONSES,
    Role.GEOMETRY_AUDITOR: ApiKind.RESPONSES,
    Role.REFERENCE_ANALYST: ApiKind.RESPONSES,
    Role.FAST_DRAFT_MAKER: ApiKind.IMAGES,
    Role.COMPOSITION_BUILDER: ApiKind.IMAGES,
    Role.REALISTIC_RENDERER: ApiKind.PROVIDER_IMAGES,
}
