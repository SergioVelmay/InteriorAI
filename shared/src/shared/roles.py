"""Roles funcionales de IA.

El código solo conoce roles; el despliegue concreto de cada rol se resuelve desde
la configuración (`DEPLOYMENT_ROLE_<ROL>`). Aquí no aparece ningún nombre comercial.
"""

from enum import StrEnum


class ApiKind(StrEnum):
    """Superficie de API de Azure AI Foundry que usa cada rol."""

    RESPONSES = "responses"  # /openai/v1/responses (texto, visión, razonamiento)
    IMAGES = "images"  # /openai/v1/images/{generations,edits}
    PROVIDER_IMAGES = "provider_images"  # /providers/<proveedor>/... (ruta propia)


class Role(StrEnum):
    PROMPT_ENGINEER = "PROMPT_ENGINEER"
    GEOMETRIC_AUDITOR = "GEOMETRIC_AUDITOR"
    REFERENCE_ANALYST = "REFERENCE_ANALYST"
    FAST_DRAFT = "FAST_DRAFT"
    STRUCTURAL_COMPOSER = "STRUCTURAL_COMPOSER"
    PHOTOREALISTIC_RENDERER = "PHOTOREALISTIC_RENDERER"

    @property
    def api_kind(self) -> ApiKind:
        return _API_KIND[self]

    @property
    def env_var(self) -> str:
        return f"DEPLOYMENT_ROLE_{self.value}"


_API_KIND: dict[Role, ApiKind] = {
    Role.PROMPT_ENGINEER: ApiKind.RESPONSES,
    Role.GEOMETRIC_AUDITOR: ApiKind.RESPONSES,
    Role.REFERENCE_ANALYST: ApiKind.RESPONSES,
    Role.FAST_DRAFT: ApiKind.IMAGES,
    Role.STRUCTURAL_COMPOSER: ApiKind.IMAGES,
    Role.PHOTOREALISTIC_RENDERER: ApiKind.PROVIDER_IMAGES,
}
