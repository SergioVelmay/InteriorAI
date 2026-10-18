"""Modelos de dominio: proyectos (un espacio de la casa) y sus assets.

Los nombres de campo están en inglés; los valores de enums, nombres de archivo/carpeta
y textos visibles, en español.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.roles import Role

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

    @property
    def label(self) -> str:
        return _ASSET_LABELS[self]


_ASSET_FOLDERS: dict[AssetKind, str] = {
    AssetKind.PLANO: "planos",
    AssetKind.REFERENCIA: "referencias",
    AssetKind.CAPTURA_SKETCHUP: "capturas_sketchup",
    AssetKind.RENDER: "renders_historico",
}

_ASSET_LABELS: dict[AssetKind, str] = {
    AssetKind.PLANO: "Plano",
    AssetKind.REFERENCIA: "Referencia",
    AssetKind.CAPTURA_SKETCHUP: "Captura de SketchUp",
    AssetKind.RENDER: "Render",
}


class _Model(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Dimensions(_Model):
    width_m: float = Field(gt=0, le=100)
    length_m: float = Field(gt=0, le=100)
    height_m: float | None = Field(default=None, gt=0, le=20)


# --- Ficha de una referencia (CONTEXT_MANAGER) ------------------------------------------


class ReferenceCategory(StrEnum):
    SOFA = "sofa"
    MESA = "mesa"
    SILLA = "silla"
    CAMA = "cama"
    ALMACENAJE = "almacenaje"
    LAMPARA = "lampara"
    ALFOMBRA = "alfombra"
    TEXTIL = "textil"
    DECORACION = "decoracion"
    REVESTIMIENTO = "revestimiento"
    AMBIENTE = "ambiente"  # inspiración de un ambiente completo
    OTRO = "otro"


class DimensionsCm(_Model):
    """Medidas en cm; `None` si no se conocen (nunca se inventan)."""

    width_cm: float | None = Field(ge=0, le=2_000)
    depth_cm: float | None = Field(ge=0, le=2_000)
    height_cm: float | None = Field(ge=0, le=2_000)


class ReferenceAnalysis(_Model):
    """Salida estructurada del CONTEXT_MANAGER para una referencia (Ikea, Pinterest...)."""

    category: ReferenceCategory
    item_name: str = Field(
        description="Qué es, en español (p. ej. 'Sofá modular con chaiselongue')"
    )
    brand: str | None = Field(description="Marca si se conoce por la nota o la imagen")
    product_name: str | None = Field(description="Nombre comercial del producto si se conoce")
    style_tags: list[str] = Field(description="Estilos, en español")
    colors: list[str] = Field(description="Colores, en español")
    materials: list[str] = Field(description="Materiales y acabados, en español")
    dimensions_cm: DimensionsCm
    dimensions_source: Literal["nota_usuario", "imagen", "desconocido"]
    summary: str = Field(description="Descripción breve en español")
    design_relevance: str = Field(
        description="Qué aporta al diseño (forma y medidas, textura, color, ambiente...)"
    )


class AssetAnalysis(_Model):
    result: ReferenceAnalysis
    status: Literal["proposed", "validated"] = "proposed"  # validated = revisado por el usuario
    prompt_version: str | None = None
    analyzed_at: datetime = Field(default_factory=utc_now)
    validated_at: datetime | None = None


class Asset(_Model):
    id: UUID = Field(default_factory=uuid4)
    kind: AssetKind
    stored_name: str
    original_name: str = Field(max_length=255)
    mime_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)
    description: str = Field(default="", max_length=2_000)  # nota del usuario (p. ej. medidas)
    analysis: AssetAnalysis | None = None  # solo referencias indexadas
    created_at: datetime = Field(default_factory=utc_now)


# --- Brief de diseño (PROMPT_ENGINEER) -----------------------------------------------


class FurnitureItem(_Model):
    name: str
    reference_asset_id: str | None = Field(
        description="id de la referencia de la que procede, o null"
    )
    dimensions_cm: DimensionsCm
    placement: str = Field(description="Ubicación en la estancia, en español")
    keep_exact: bool = Field(description="True si forma y medidas deben respetarse con exactitud")


class ImagePrompts(_Model):
    """Prompts para los modelos de imagen, en inglés."""

    fast_draft: str
    structural_composer: str
    photorealistic_renderer: str


class DesignBriefContent(_Model):
    """Salida estructurada del PROMPT_ENGINEER (editable por el usuario)."""

    title: str
    summary: str = Field(description="Resumen del diseño, en español")
    spatial_constraints: list[str] = Field(description="Cotas, huecos y pasos libres, en español")
    furniture: list[FurnitureItem]
    palette: list[str]
    materials: list[str]
    lighting: str
    camera: str = Field(description="Punto de vista propuesto, en español")
    image_prompts: ImagePrompts
    open_questions: list[str] = Field(description="Dudas para el usuario, en español")


class BriefStatus(StrEnum):
    PROPOSED = "propuesto"
    APPROVED = "aprobado"
    REJECTED = "rechazado"
    SUPERSEDED = "reemplazado"  # había sido aprobado y se aprobó una versión posterior


class DesignBrief(_Model):
    id: UUID = Field(default_factory=uuid4)
    version: int = Field(ge=1)
    status: BriefStatus = BriefStatus.PROPOSED
    content: DesignBriefContent
    instructions: str = ""  # indicaciones del usuario para esta versión
    feedback: str | None = None  # motivo del rechazo (alimenta la siguiente versión)
    parent_id: UUID | None = None
    source_asset_ids: list[UUID] = Field(default_factory=list)  # planos/capturas enviados
    reference_asset_ids: list[UUID] = Field(default_factory=list)  # fichas incluidas
    warnings: list[str] = Field(default_factory=list)
    prompt_version: str | None = None
    request_id: str | None = None  # petición que lo generó (coste en la telemetría)
    edited_by_user: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    decided_at: datetime | None = None


# --- Renders (pipelines de imagen) ------------------------------------------------------


class RenderStage(StrEnum):
    DRAFT = "boceto"  # FAST_DRAFT
    COMPOSITION = "composicion"  # STRUCTURAL_COMPOSER
    FINAL = "render_final"  # PHOTOREALISTIC_RENDERER

    @property
    def label(self) -> str:
        return {"boceto": "Boceto", "composicion": "Composición", "render_final": "Render final"}[
            self.value
        ]


class RenderStatus(StrEnum):
    GENERATED = "generado"
    SELECTED = "seleccionado"  # elegido por el usuario: puede alimentar la etapa siguiente
    DISCARDED = "descartado"
    REJECTED = "rechazado"  # rechazado con comentarios (puede regenerarse)


# --- Auditoría geométrica (GEOMETRIC_AUDITOR) --------------------------------------------


class AuditCheck(_Model):
    aspect: Literal[
        "encuadre", "proporciones", "mobiliario", "elementos_fijos", "materiales_color",
        "iluminacion",
    ]  # fmt: skip
    status: Literal["ok", "aviso", "fallo"]
    finding: str = Field(description="Hallazgo concreto, en español")


class AuditDeviation(_Model):
    element: str
    expected: str = Field(description="Lo que indica la captura o el brief, en español")
    observed: str = Field(description="Lo que se ve en la imagen auditada, en español")
    severity: Literal["baja", "media", "alta"]


class AuditReport(_Model):
    """Salida estructurada del GEOMETRIC_AUDITOR."""

    verdict: Literal["conforme", "conforme_con_observaciones", "no_conforme"]
    score: int = Field(ge=0, le=100, description="Fidelidad global a la captura y al brief")
    checks: list[AuditCheck]
    deviations: list[AuditDeviation]
    suggested_prompt_adjustments: str = Field(
        description="Correcciones para la siguiente iteración, EN INGLÉS; vacío si no hacen falta"
    )
    summary: str = Field(description="Resumen en español")


class RenderAudit(_Model):
    id: UUID = Field(default_factory=uuid4)
    report: AuditReport
    reference_asset_id: UUID  # captura/plano con la que se comparó
    deployment: str
    reasoning_effort: str
    prompt_version: str
    request_id: str | None = None
    cost_eur: float | None = None
    created_at: datetime = Field(default_factory=utc_now)


class RenderInpaint(_Model):
    """Retoque de una zona: la imagen es `source_render_id` con solo la zona pintada cambiada."""

    source_render_id: UUID  # imagen retocada (no cambia)
    instruction: str  # cambio pedido por el usuario
    mask_file: str  # máscara normalizada junto al render (blanco = zona editada)
    raw_file: str | None = None  # salida del modelo tal cual, antes de recomponer
    guide_file: str | None = None  # imagen guía enviada al renderizador (zona en rojo)
    coverage: float = Field(ge=0, le=1)  # fracción de la imagen pintada
    feather_px: int = Field(ge=0)  # suavizado del borde al recomponer
    method: Literal["mascara", "regeneracion"]  # máscara nativa o imagen completa + recorte

    @property
    def files(self) -> list[str]:
        """Archivos del retoque guardados junto al render en `renders_historico/`."""
        return [f for f in (self.mask_file, self.raw_file, self.guide_file) if f]


class RenderRecord(_Model):
    """Trazabilidad de una imagen generada. `id` coincide con el del asset `render`."""

    id: UUID
    stage: RenderStage
    status: RenderStatus = RenderStatus.GENERATED
    role: Role
    deployment: str
    brief_id: UUID
    brief_version: int
    prompt: str  # prompt exacto enviado al modelo
    input_asset_ids: list[UUID]  # imagen base y referencias, en orden
    parent_render_id: UUID | None = None  # render de la etapa anterior del que deriva
    batch_id: UUID  # renders generados en la misma llamada
    size: str
    quality: str | None = None
    seed: int | None = None
    request_id: str | None = None
    cost_eur: float | None = None  # coste estimado de la llamada repartido entre sus imágenes
    audits: list[RenderAudit] = Field(default_factory=list)  # a demanda; la última es la vigente
    feedback: str | None = None  # comentarios del usuario al rechazar
    previous_attempt_id: UUID | None = None  # render rechazado que esta imagen sustituye
    inpaint: RenderInpaint | None = None  # solo si es un retoque de zona (Paso 13b)
    raw_of_render_id: UUID | None = None  # salida en bruto de ese retoque, como imagen propia
    created_at: datetime = Field(default_factory=utc_now)
    decided_at: datetime | None = None


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

    @model_validator(mode="after")
    def _required_fields_not_null(self) -> ProjectUpdate:
        for field in ("name", "space_type"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"'{field}' no puede ser null")
        return self

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
    briefs: list[DesignBrief] = Field(default_factory=list)
    renders: list[RenderRecord] = Field(default_factory=list)

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


AiOperation = Literal["complete_text", "generate_image", "edit_image"]


class TelemetryRecord(_Model):
    """Una llamada a la IA: tokens, imágenes, latencia y coste estimado."""

    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=utc_now)
    request_id: str | None = None  # X-Request-ID de la petición HTTP que la originó
    role: Role
    deployment: str
    operation: AiOperation
    status: Literal["ok", "error"]
    error_type: str | None = None
    latency_s: float = Field(ge=0)
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    input_text_tokens: int = 0
    input_image_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    images_out: int = 0
    megapixels_out: float = 0.0
    megapixels_ref: float = 0.0
    cost_eur: float | None = None  # None = despliegue sin precio en pricing.yaml
    cost_breakdown: dict[str, float] = Field(default_factory=dict)
    pricing_tier: str | None = None
    simulated: bool = False  # True en AI_PROVIDER_MODE=mock


class TelemetryLog(_Model):
    """Contenido de `{id}/costes_telemetria.json`."""

    schema_version: Literal[1] = SCHEMA_VERSION
    records: list[TelemetryRecord] = Field(default_factory=list)
