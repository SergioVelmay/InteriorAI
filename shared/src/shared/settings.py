"""Configuración central de InteriorAI (Pydantic Settings).

Todo se lee del entorno o de `.env`. Cada sección es un `BaseSettings` con su propio
prefijo de variables; `Settings` las agrega y valida las reglas entre secciones.

Comprobar el `.env` local (la clave se muestra enmascarada):

    uv run python -m shared
"""

from __future__ import annotations

import os
import sys
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.roles import RENAMED_ROLES, Role

DEFAULT_ENV_FILE = Path(".env")


def _legacy_names() -> dict[str, str]:
    """Variables con el nombre anterior de un rol → nombre actual (Pasos 18 y 26)."""
    names = {f"DEPLOYMENT_ROLE_{old}": role.env_var for old, role in RENAMED_ROLES.items()}
    names["PROMPT_ENGINEER_REASONING_EFFORT"] = "PROMPT_ARCHITECT_REASONING_EFFORT"
    names["GEOMETRIC_AUDITOR_REASONING_EFFORT"] = "GEOMETRY_AUDITOR_REASONING_EFFORT"
    names["GEOMETRIC_AUDITOR_TIMEOUT_S"] = "GEOMETRY_AUDITOR_TIMEOUT_S"
    return names


LEGACY_ENV_VARS = _legacy_names()


def legacy_env_vars(env_file: Path | None = DEFAULT_ENV_FILE) -> dict[str, str]:
    """Variables con un nombre anterior presentes en el entorno o en `env_file` → su nombre
    actual. Desde la 3.0.0 no se usan (decisión del usuario): solo se avisa."""
    present = {name.upper() for name in os.environ}
    if env_file is not None and env_file.is_file():
        present |= {name.upper() for name in dotenv_values(env_file)}
    return {old: new for old, new in LEGACY_ENV_VARS.items() if old in present}


def legacy_env_warning(legacy: dict[str, str]) -> str | None:
    if not legacy:
        return None
    pairs = ", ".join(f"{old} → {new}" for old, new in legacy.items())
    return f"Variables con el nombre anterior de un rol, que ya no se usan: renómbralas ({pairs})"


class ProviderMode(StrEnum):
    MOCK = "mock"
    AZURE = "azure"


def _config(prefix: str = "") -> SettingsConfigDict:
    return SettingsConfigDict(
        env_prefix=prefix,
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


def _blank_to_none(value: Any) -> Any:
    """`VAR=` en `.env` llega como cadena vacía: se trata como no definida."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


class AppSettings(BaseSettings):
    model_config = _config()

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    ai_provider_mode: ProviderMode = ProviderMode.MOCK

    @field_validator("app_env", "ai_provider_mode", mode="before")
    @classmethod
    def _lower(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value


class FoundrySettings(BaseSettings):
    model_config = _config("AZURE_FOUNDRY_")

    endpoint: str | None = None
    api_key: SecretStr | None = None
    api_version: str | None = None
    renderer_endpoint: str | None = None
    renderer_path: str | None = None
    # La API del proveedor del renderizador (/providers/...) exige api-version (B-003).
    renderer_api_version: str | None = "preview"
    timeout_s: float = Field(default=120, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)

    @field_validator(
        "endpoint",
        "api_key",
        "api_version",
        "renderer_endpoint",
        "renderer_path",
        "renderer_api_version",
        mode="before",
    )
    @classmethod
    def _blank(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("endpoint", "renderer_endpoint")
    @classmethod
    def _base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value.strip())
        if parts.scheme != "https" or not parts.netloc:
            raise ValueError(
                "debe ser una URL https, p. ej. https://<recurso>.services.ai.azure.com"
            )
        if parts.path.strip("/") or parts.query or parts.fragment:
            raise ValueError(
                "debe ser solo el host, sin ruta ni parámetros (quita '/openai/v1/...'); "
                "la ruta de cada API la añade el código"
            )
        return f"https://{parts.netloc}"

    @field_validator("renderer_path")
    @classmethod
    def _path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value.startswith("/") or "://" in value:
            raise ValueError(
                "debe ser una ruta que empiece por '/', p. ej. /providers/<...>/v1/<...>"
            )
        return value.rstrip("/")

    @property
    def renderer_base_url(self) -> str | None:
        """Endpoint del renderizador; si no se define, el principal."""
        return self.renderer_endpoint or self.endpoint


class DeploymentSettings(BaseSettings):
    """Despliegue asociado a cada rol (`DEPLOYMENT_ROLE_<ROL>`)."""

    model_config = _config("DEPLOYMENT_ROLE_")

    prompt_architect: str | None = None
    geometry_auditor: str | None = None
    reference_analyst: str | None = None
    fast_draft_maker: str | None = None
    composition_builder: str | None = None
    realistic_renderer: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _blank(cls, value: Any) -> Any:
        value = _blank_to_none(value)
        return value.strip() if isinstance(value, str) else value

    def get(self, role: Role) -> str | None:
        return getattr(self, role.value.lower())


class AuditorSettings(BaseSettings):
    model_config = _config("GEOMETRY_AUDITOR_")

    # `max` verificado en el Paso 6 (B-001); el usuario lo fija en `medium` (Paso 10): la
    # auditoría es opcional y `max` dispara latencia y coste.
    reasoning_effort: str = Field(default="medium", min_length=1)
    # Timeout propio: las auditorías con razonamiento tardan minutos (120 s no bastan).
    timeout_s: float = Field(default=900, gt=0)

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def _lower(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value


class ReasoningSettings(BaseSettings):
    """Esfuerzo de razonamiento de los demás roles de texto (`<ROL>_REASONING_EFFORT`, B-053);
    el del auditor está en `AuditorSettings`. El razonamiento se factura como salida."""

    model_config = _config()

    prompt_architect_reasoning_effort: str = Field(default="medium", min_length=1)
    reference_analyst_reasoning_effort: str = Field(default="medium", min_length=1)
    # Timeout propio del PROMPT_ARCHITECT (Paso 32): con `high`, un prompt de bocetos tardó 102 s,
    # al borde de los 120 s del cliente (los timeouts no se reintentan).
    prompt_architect_timeout_s: float = Field(default=300, gt=0)

    @field_validator("*", mode="before")
    @classmethod
    def _lower(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value


class CostAlertSettings(BaseSettings):
    """Umbrales de aviso de gasto real de IA (B-021): solo avisan, nunca bloquean."""

    model_config = _config("COST_ALERT_")

    project_eur: float = Field(default=3.0, gt=0)  # por proyecto
    total_eur: float = Field(default=10.0, gt=0)  # suma de todos los proyectos


class StorageSettings(BaseSettings):
    model_config = _config()

    data_dir: Path = Path("/app/data")
    pricing_file: Path = Path("/app/config/pricing.yaml")
    max_upload_mb: int = Field(default=25, gt=0, le=200)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


class NetworkSettings(BaseSettings):
    model_config = _config()

    backend_host: str = "0.0.0.0"  # noqa: S104 — dentro del contenedor; el host lo limita compose
    backend_port: int = Field(default=8000, ge=1, le=65535)
    backend_url: str = "http://backend:8000"
    frontend_port: int = Field(default=7860, ge=1, le=65535)

    @field_validator("backend_url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        parts = urlsplit(value.strip())
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("debe ser una URL http(s), p. ej. http://backend:8000")
        return value.strip().rstrip("/")


class Settings(BaseModel):
    """Configuración completa y validada de la aplicación."""

    model_config = ConfigDict(frozen=True)

    app: AppSettings
    foundry: FoundrySettings
    deployments: DeploymentSettings
    auditor: AuditorSettings
    reasoning: ReasoningSettings
    cost_alerts: CostAlertSettings
    storage: StorageSettings
    network: NetworkSettings
    # Variables con el nombre anterior de un rol (no se usan; ver `legacy_env_vars`)
    legacy_env: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def load(cls, env_file: Path | None = DEFAULT_ENV_FILE) -> Settings:
        """Carga desde entorno + `env_file` (None = solo variables de entorno)."""
        kwargs: dict[str, Any] = {"_env_file": env_file}
        return cls(
            legacy_env=legacy_env_vars(env_file),
            app=AppSettings(**kwargs),
            foundry=FoundrySettings(**kwargs),
            deployments=DeploymentSettings(**kwargs),
            auditor=AuditorSettings(**kwargs),
            reasoning=ReasoningSettings(**kwargs),
            cost_alerts=CostAlertSettings(**kwargs),
            storage=StorageSettings(**kwargs),
            network=NetworkSettings(**kwargs),
        )

    @property
    def is_mock(self) -> bool:
        return self.app.ai_provider_mode is ProviderMode.MOCK

    def azure_missing(self) -> list[str]:
        """Variables obligatorias para `AI_PROVIDER_MODE=azure` que faltan."""
        missing = [
            name
            for name, value in (
                ("AZURE_FOUNDRY_ENDPOINT", self.foundry.endpoint),
                ("AZURE_FOUNDRY_API_KEY", self.foundry.api_key),
                ("AZURE_FOUNDRY_RENDERER_PATH", self.foundry.renderer_path),
            )
            if value is None
        ]
        missing += [role.env_var for role in Role if not self.deployments.get(role)]
        return missing

    @model_validator(mode="after")
    def _require_azure_config(self) -> Settings:
        if not self.is_mock and (missing := self.azure_missing()):
            message = "AI_PROVIDER_MODE=azure requiere: " + ", ".join(missing)
            if warning := legacy_env_warning(self.legacy_env):
                message += f". {warning}"
            raise ValueError(message)
        return self

    def reasoning_effort(self, role: Role) -> str | None:
        """Esfuerzo de razonamiento de un rol de texto; None en los roles de imagen."""
        return {
            Role.PROMPT_ARCHITECT: self.reasoning.prompt_architect_reasoning_effort,
            Role.REFERENCE_ANALYST: self.reasoning.reference_analyst_reasoning_effort,
            Role.GEOMETRY_AUDITOR: self.auditor.reasoning_effort,
        }.get(role)

    def timeout_for(self, role: Role) -> float | None:
        """Timeout propio de un rol (auditor y PROMPT_ARCHITECT); None = el del cliente."""
        return {
            Role.GEOMETRY_AUDITOR: self.auditor.timeout_s,
            Role.PROMPT_ARCHITECT: self.reasoning.prompt_architect_timeout_s,
        }.get(role)

    def deployment_for(self, role: Role) -> str:
        """Único punto para obtener el despliegue de un rol."""
        if name := self.deployments.get(role):
            return name
        if self.is_mock:
            return f"mock-{role.value.lower()}"
        raise LookupError(f"{role.env_var} no está configurado")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()


# --- Comprobación por CLI ----------------------------------------------------------


def _mask(secret: SecretStr | None) -> str:
    if secret is None:
        return "(vacía)"
    raw = secret.get_secret_value()
    return f"****{raw[-4:]} ({len(raw)} caracteres)" if len(raw) > 8 else "****"


def _mark(ok: bool) -> str:
    return "[OK]" if ok else "[--]"


def render_report(s: Settings) -> str:
    f = s.foundry
    lines = [
        "InteriorAI - configuración",
        "",
        f"  Modo IA ............ {s.app.ai_provider_mode.value}",
        f"  Entorno / log ...... {s.app.app_env} / {s.app.log_level}",
        "",
        "  Azure AI Foundry",
        f"    {_mark(f.endpoint is not None)} Endpoint ......... {f.endpoint or '(vacío)'}",
        f"    {_mark(f.api_key is not None)} API key .......... {_mask(f.api_key)}",
        f"         API version ...... {f.api_version or '(no usada: API v1)'}",
        f"    {_mark(f.renderer_base_url is not None)} Renderer endpoint  "
        f"{f.renderer_endpoint or '(usa el principal)'}",
        f"    {_mark(f.renderer_path is not None)} Renderer path .... "
        f"{f.renderer_path or '(vacío)'}",
        f"         Renderer api-version {f.renderer_api_version or '(ninguna)'}",
        f"         Timeout / reintentos {f.timeout_s:g}s / {f.max_retries}",
        "",
        "  Despliegues por rol",
    ]
    for role in Role:
        name = s.deployments.get(role)
        lines.append(
            f"    {_mark(name is not None)} {role.value:<24} -> {name or '(vacío)'}"
            f"  [{role.api_kind.value}]"
        )
    lines += [
        "",
        "  Razonamiento: "
        + " | ".join(
            f"{role.value} {s.reasoning_effort(role)}"
            for role in Role
            if s.reasoning_effort(role) is not None
        ),
        f"  Timeouts propios: auditor {s.auditor.timeout_s:g}s | PROMPT_ARCHITECT "
        f"{s.reasoning.prompt_architect_timeout_s:g}s",
        f"  Avisos de gasto: {s.cost_alerts.project_eur:g} € por proyecto "
        f"| {s.cost_alerts.total_eur:g} € en total",
        f"  Datos: {s.storage.data_dir.as_posix()} | precios: {s.storage.pricing_file.as_posix()} "
        f"| upload máx: {s.storage.max_upload_mb} MB",
        f"  Backend: {s.network.backend_host}:{s.network.backend_port} "
        f"| URL interna: {s.network.backend_url} | frontend: {s.network.frontend_port}",
        "",
    ]
    if warning := legacy_env_warning(s.legacy_env):
        lines += [f"  [!!] {warning}", ""]
    missing = s.azure_missing()
    if missing:
        lines.append("  Listo para modo azure: NO - faltan " + ", ".join(missing))
    else:
        lines.append("  Listo para modo azure: SÍ")
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        settings = Settings.load()
    except ValidationError as exc:
        # Solo ubicación y mensaje: nunca el valor de entrada (podría ser un secreto).
        print("[!!] Configuración inválida:")
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "config"
            print(f"  - {loc}: {err['msg']}")
        return 1
    print(render_report(settings))
    return 0
