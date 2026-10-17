"""Código común de InteriorAI: configuración, roles y modelos compartidos."""

from shared.roles import ApiKind, Role
from shared.settings import ProviderMode, Settings, get_settings

__all__ = ["ApiKind", "ProviderMode", "Role", "Settings", "get_settings"]
