"""Modelos de dominio: proyectos (un espacio de la casa) y sus assets.

Los nombres de campo están en inglés; los valores de enums, nombres de archivo/carpeta
y textos visibles, en español.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


def utc_now() -> datetime:
    return datetime.now(UTC)


class SpaceType(StrEnum):
    SALON_COCINA_COMEDOR = "salon_cocina_comedor"
    SALON = "salon"
    COCINA = "cocina"
    COMEDOR = "comedor"
    DORMITORIO = "dormitorio"
    ESTUDIO = "estudio"
    BANO = "bano"
    TERRAZA = "terraza"
    OTRO = "otro"

    @property
    def label(self) -> str:
        return _SPACE_LABELS[self]


_SPACE_LABELS: dict[SpaceType, str] = {
    SpaceType.SALON_COCINA_COMEDOR: "Salón-cocina-comedor",
    SpaceType.SALON: "Salón",
    SpaceType.COCINA: "Cocina",
    SpaceType.COMEDOR: "Comedor",
    SpaceType.DORMITORIO: "Dormitorio",
    SpaceType.ESTUDIO: "Estudio",
    SpaceType.BANO: "Baño",
    SpaceType.TERRAZA: "Terraza",
    SpaceType.OTRO: "Otro",
}


class AssetKind(StrEnum):
    PLANO = "plano"
    REFERENCIA = "referencia"
    CAPTURA_SKETCHUP = "captura_sketchup"
    RENDER = "render"

    @property
    def folder(self) -> str:
        """Subcarpeta del proyecto donde se guardan los assets de este tipo."""
        return _ASSET_FOLDERS[self]


_ASSET_FOLDERS: dict[AssetKind, str] = {
    AssetKind.PLANO: "planos",
    AssetKind.REFERENCIA: "referencias",
    AssetKind.CAPTURA_SKETCHUP: "capturas_sketchup",
    AssetKind.RENDER: "renders_historico",
}


class _Model(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Dimensions(_Model):
    width_m: float = Field(gt=0, le=100)
    length_m: float = Field(gt=0, le=100)
    height_m: float | None = Field(default=None, gt=0, le=20)


class Asset(_Model):
    id: UUID = Field(default_factory=uuid4)
    kind: AssetKind
    stored_name: str
    original_name: str = Field(max_length=255)
    mime_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime = Field(default_factory=utc_now)


class ProjectFields(_Model):
    """Campos editables por el usuario."""

    name: str = Field(min_length=1, max_length=120)
    space_type: SpaceType
    description: str = Field(default="", max_length=2_000)
    design_notes: str = Field(default="", max_length=20_000)
    dimensions: Dimensions | None = None
    style: str = Field(default="", max_length=200)
    budget_eur: float | None = Field(default=None, ge=0)


class ProjectCreate(ProjectFields):
    pass


class ProjectUpdate(_Model):
    """Actualización parcial: solo se aplican los campos enviados."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    space_type: SpaceType | None = None
    description: str | None = Field(default=None, max_length=2_000)
    design_notes: str | None = Field(default=None, max_length=20_000)
    dimensions: Dimensions | None = None
    style: str | None = Field(default=None, max_length=200)
    budget_eur: float | None = Field(default=None, ge=0)

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class ProjectSummary(_Model):
    """Entrada del índice global `proyectos.json`."""

    id: UUID
    name: str
    space_type: SpaceType
    created_at: datetime
    updated_at: datetime


class ProjectMetadata(ProjectFields):
    """Contenido de `{id}/metadatos.json`."""

    schema_version: Literal[1] = SCHEMA_VERSION
    id: UUID
    created_at: datetime
    updated_at: datetime
    assets: list[Asset] = Field(default_factory=list)

    def summary(self) -> ProjectSummary:
        return ProjectSummary(
            id=self.id,
            name=self.name,
            space_type=self.space_type,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class ProjectIndex(_Model):
    """Contenido de `proyectos.json`."""

    schema_version: Literal[1] = SCHEMA_VERSION
    projects: list[ProjectSummary] = Field(default_factory=list)


class TelemetryLog(_Model):
    """Contenido de `{id}/costes_telemetria.json` (registros tipados en el Paso 7)."""

    schema_version: Literal[1] = SCHEMA_VERSION
    records: list[dict[str, Any]] = Field(default_factory=list)
