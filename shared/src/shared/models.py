"""Modelos de dominio: proyectos (un espacio de la casa) y sus assets.

Los nombres de campo están en inglés; los valores de enums, nombres de archivo/carpeta
y textos visibles, en español.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shared.roles import Role, current_role

SCHEMA_VERSION = 2  # 1 → 2: modelo de datos de la versión 2.0.0 (Paso 17)
# Cabe la descripción de cualquier proyecto migrado (descripción + notas de diseño de la v1).
DESCRIPTION_MAX = 25_000


def utc_now() -> datetime:
    return datetime.now(UTC)


class AssetKind(StrEnum):
    """Tipo de asset. Desde la v2 (B-028), toda imagen subida es una referencia."""

    REFERENCIA = "referencia"
    RENDER = "render"

    @property
    def folder(self) -> str:
        """Subcarpeta del proyecto donde se guardan los assets de este tipo."""
        return _ASSET_FOLDERS[self]

    @property
    def label(self) -> str:
        return _ASSET_LABELS[self]


_ASSET_FOLDERS: dict[AssetKind, str] = {
    AssetKind.REFERENCIA: "referencias",
    AssetKind.RENDER: "renders_historico",
}

_ASSET_LABELS: dict[AssetKind, str] = {
    AssetKind.REFERENCIA: "Referencia",
    AssetKind.RENDER: "Render",
}

# Tipo que tenía en la v1 una imagen migrada: puente hasta el Paso 22, donde se elige la imagen
# de partida. Mientras tanto sigue siendo la base de los bocetos, del brief y de la auditoría.
LegacyKind = Literal["captura_sketchup", "plano"]
LEGACY_KIND_LABELS: dict[str, str] = {"captura_sketchup": "Captura de SketchUp", "plano": "Plano"}


class _Model(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class DimensionsCm(_Model):
    """Medidas en cm; `None` si no se conocen. Nunca se inventan: una estimación solo se
    admite marcada como tal (`dimensions_source: "estimada"`) y nunca se trata como exacta."""

    width_cm: float | None = Field(ge=0, le=2_000)
    depth_cm: float | None = Field(ge=0, le=2_000)
    height_cm: float | None = Field(ge=0, le=2_000)


# --- Receta y ficha de una referencia (REFERENCE_ANALYST, v2: B-029 y B-030) ----------------

MeasureSource = Literal["nota_usuario", "cota_imagen", "estimada", "ninguna"]


class RecipeElement(_Model):
    """Un «ingrediente» de la receta: algo concreto que la imagen puede aportar al diseño."""

    label: str = Field(description="Qué es, breve y concreto, en español")
    detail: str = Field(description="Detalle útil para reproducirlo, en español; vacío si no hay")
    dimensions_cm: DimensionsCm
    dimensions_source: MeasureSource = Field(
        description="nota_usuario | cota_imagen (legible en la imagen) | estimada (aproximada, "
        "nunca exacta) | ninguna"
    )
    selected: bool = Field(description="True si las notas del usuario piden este elemento")


class ReferenceRecipe(_Model):
    """Receta de una imagen de referencia: grupos fijos y exhaustivos, con «otros» para lo no
    previsto. El orden de los elementos de cada grupo sigue las prioridades de las notas."""

    summary: str = Field(description="Qué es la imagen y qué aporta, en una o dos frases")
    objetos: list[RecipeElement]
    decoracion: list[RecipeElement]
    colores: list[RecipeElement]
    materiales: list[RecipeElement]
    arquitectura: list[RecipeElement]
    estilo: list[RecipeElement]
    iluminacion: list[RecipeElement]
    perspectiva: list[RecipeElement]
    geometria: list[RecipeElement]
    ambiente: list[RecipeElement]
    fotografia: list[RecipeElement]
    otros: list[RecipeElement]

    def elements(self) -> list[tuple[str, RecipeElement]]:
        """(id, elemento) de todos los grupos; id = «grupo:índice»."""
        return [
            (f"{group}:{i}", element)
            for group in RECIPE_GROUPS
            for i, element in enumerate(getattr(self, group))
        ]


# Grupos de la receta, en orden, con su etiqueta visible.
RECIPE_GROUPS: dict[str, str] = {
    "objetos": "Objetos y mobiliario",
    "decoracion": "Decoración, textiles y plantas",
    "colores": "Colores y paleta",
    "materiales": "Materiales, texturas y acabados",
    "arquitectura": "Elementos arquitectónicos (suelos, paredes, techos, carpinterías)",
    "estilo": "Estilo y referencias de diseño",
    "iluminacion": "Iluminación",
    "perspectiva": "Perspectiva y punto de vista",
    "geometria": "Medidas y geometría del espacio",
    "ambiente": "Ambiente y atmósfera",
    "fotografia": "Fotografía y tratamiento de la imagen",
    "otros": "Otros",
}


class ReferenceSheet(_Model):
    """Ficha guardada de una referencia: su receta y los elementos marcados por el usuario.
    Guardada desde el análisis (con lo que piden las notas ya marcado); activa si hay algo
    marcado. Solo las referencias activas se usan en el diseño."""

    recipe: ReferenceRecipe
    selected: list[str] = Field(default_factory=list)  # ids «grupo:índice»
    notes: str = ""  # notas con las que se analizó
    prompt_version: str | None = None
    request_id: str | None = None  # petición del análisis (coste en la telemetría)
    deployment: str | None = None
    analyzed_at: datetime = Field(default_factory=utc_now)
    saved_at: datetime = Field(default_factory=utc_now)

    @property
    def active(self) -> bool:
        return bool(self.selected)

    def selected_elements(self) -> dict[str, list[RecipeElement]]:
        """Lo marcado, por grupo (solo grupos con algo marcado)."""
        chosen = set(self.selected)
        groups: dict[str, list[RecipeElement]] = {}
        for element_id, element in self.recipe.elements():
            if element_id in chosen:
                groups.setdefault(element_id.split(":")[0], []).append(element)
        return groups

    def unselected_elements(self) -> dict[str, list[RecipeElement]]:
        """Lo NO marcado, por grupo: lo que el modelo de imagen ve en la referencia pero no
        debe tomar (Paso 28, B-068)."""
        chosen = set(self.selected)
        groups: dict[str, list[RecipeElement]] = {}
        for element_id, element in self.recipe.elements():
            if element_id not in chosen:
                groups.setdefault(element_id.split(":")[0], []).append(element)
        return groups


# --- Ficha de la v1 (histórico; ya no se genera) ----------------------------------------------


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


class ReferenceAnalysis(_Model):
    """Salida estructurada del REFERENCE_ANALYST para una referencia (Ikea, Pinterest...)."""

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
    request_id: str | None = None  # petición que la generó (coste en la telemetría)


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
    description: str = Field(default="", max_length=2_000)  # notas: orientan el análisis
    sheet: ReferenceSheet | None = None  # receta y ficha (v2); None si aún no se ha analizado
    analysis: AssetAnalysis | None = None  # histórico (v1): ficha anterior, ya no se usa
    legacy_kind: LegacyKind | None = None  # solo imágenes migradas de la v1 (ver arriba)
    created_at: datetime = Field(default_factory=utc_now)


# --- Brief de diseño (PROMPT_ARCHITECT) -----------------------------------------------


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
    """Salida estructurada del PROMPT_ARCHITECT (editable por el usuario)."""

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
    source_asset_ids: list[UUID] = Field(default_factory=list)  # imágenes base enviadas
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
    DRAFT = "boceto"  # FAST_DRAFT_MAKER
    COMPOSITION = "composicion"  # COMPOSITION_BUILDER
    FINAL = "render_final"  # REALISTIC_RENDERER

    @property
    def label(self) -> str:
        return {"boceto": "Boceto", "composicion": "Composición", "render_final": "Render final"}[
            self.value
        ]


class RenderStatus(StrEnum):
    """Sin estados de rechazo ni descarte desde la v2 (B-048): las imágenes se generan y,
    como mucho, se seleccionan."""

    GENERATED = "generado"
    SELECTED = "seleccionado"  # elegido por el usuario: puede alimentar la etapa siguiente


# --- Auditoría geométrica (GEOMETRY_AUDITOR) --------------------------------------------


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
    """Salida estructurada del GEOMETRY_AUDITOR."""

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
    reference_asset_id: UUID | None = None  # v1: captura/plano de origen con la que se comparó
    # Paso 23: las referencias del espacio (perspectiva o geometría marcadas) comparadas
    reference_asset_ids: list[UUID] = Field(default_factory=list)
    notes: str = ""  # observaciones del usuario que el auditor debía comprobar
    deployment: str
    reasoning_effort: str
    prompt_version: str
    request_id: str | None = None
    cost_eur: float | None = None
    created_at: datetime = Field(default_factory=utc_now)


class RenderInpaint(_Model):
    """Retoque de una zona de una composición con máscara nativa (B-038): la imagen es la que
    devuelve el modelo, completa. Los retoques de la v1 recomponían solo la zona pintada sobre
    `source_render_id` y podían ser de renders finales (`regeneracion`)."""

    source_render_id: UUID  # imagen retocada (no cambia)
    instruction: str  # cambio pedido por el usuario
    mask_file: str  # máscara normalizada junto al render (blanco = zona editada)
    raw_file: str | None = None  # histórico (v1): salida del modelo antes de recomponer
    guide_file: str | None = None  # histórico (v1): guía enviada al renderizador (zona en rojo)
    coverage: float = Field(ge=0, le=1)  # fracción de la imagen pintada
    feather_px: int | None = Field(default=None, ge=0)  # histórico (v1): borde al recomponer
    method: Literal["mascara", "regeneracion"] = "mascara"  # regeneracion: render final (v1)

    @property
    def files(self) -> list[str]:
        """Archivos del retoque guardados junto al render en `renders_historico/`."""
        return [f for f in (self.mask_file, self.raw_file, self.guide_file) if f]


class StagePrompt(_Model):
    """Prompt automático de una generación (Paso 22: sustituye al brief). El PROMPT_ARCHITECT lo
    escribe al generar, con las entradas reales de la etapa, y explica lo que ha entendido."""

    prompt: str = Field(description="Prompt para el modelo de imagen, EN INGLÉS")
    interpretation: str = Field(
        description="Lo que has entendido y cómo lo traduces, en español, para el usuario"
    )
    open_questions: list[str] = Field(
        description="Dudas o contradicciones que el usuario debería aclarar, en español"
    )


class RenderRecord(_Model):
    """Trazabilidad de una imagen generada. `id` coincide con el del asset `render`."""

    id: UUID
    stage: RenderStage
    status: RenderStatus = RenderStatus.GENERATED
    role: Role
    deployment: str
    brief_id: UUID | None = None  # histórico (v1): brief del que salió; None desde el Paso 22
    brief_version: int | None = None
    prompt: str  # prompt exacto enviado al modelo
    prompt_info: StagePrompt | None = None  # cómo se escribió el prompt (Paso 22)
    prompt_version: str | None = None  # versión del prompt de sistema que lo escribió
    input_asset_ids: list[UUID]  # imagen base y referencias, en orden
    parent_render_id: UUID | None = None  # render de la etapa anterior del que deriva
    # «Otra versión» (Paso 24, B-051): render final cuyo prompt, partida y tamaño se repiten
    variant_of_id: UUID | None = None
    batch_id: UUID  # renders generados en la misma llamada
    size: str
    quality: str | None = None
    seed: int | None = None
    request_id: str | None = None
    cost_eur: float | None = None  # coste estimado de la llamada repartido entre sus imágenes
    audits: list[RenderAudit] = Field(default_factory=list)  # a demanda; la última es la vigente
    feedback: str | None = None  # histórico (v1): comentarios del usuario al rechazarla
    previous_attempt_id: UUID | None = None  # histórico (v1): render rechazado al que sustituye
    inpaint: RenderInpaint | None = None  # solo si es un retoque de zona (Paso 13b)
    raw_of_render_id: UUID | None = None  # histórico (v1): salida en bruto de ese retoque
    created_at: datetime = Field(default_factory=utc_now)
    decided_at: datetime | None = None

    @field_validator("role", mode="before")
    @classmethod
    def _renamed_role(cls, value: Any) -> Any:
        """Roles renombrados (Paso 26, B-057): las imágenes anteriores se leen con el nombre
        actual sin reescribir `metadatos.json`."""
        return current_role(value)


class ProjectFields(_Model):
    """Campos editables por el usuario. La descripción es el contexto del diseño (B-026)."""

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=DESCRIPTION_MAX)


class ProjectCreate(ProjectFields):
    pass


class ProjectUpdate(_Model):
    """Actualización parcial: solo se aplican los campos enviados."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)

    @model_validator(mode="after")
    def _required_fields_not_null(self) -> ProjectUpdate:
        for field in ("name", "description"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"'{field}' no puede ser null")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class ProjectSummary(_Model):
    """Entrada del índice global `proyectos.json`."""

    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


class ProjectMetadata(ProjectFields):
    """Contenido de `{id}/metadatos.json`."""

    schema_version: Literal[2] = SCHEMA_VERSION
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
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class ProjectIndex(_Model):
    """Contenido de `proyectos.json`."""

    schema_version: Literal[2] = SCHEMA_VERSION
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

    @field_validator("role", mode="before")
    @classmethod
    def _renamed_role(cls, value: Any) -> Any:
        """Roles renombrados (Pasos 18 y 26): los registros anteriores se leen con el nombre
        actual en lugar de reescribirlos (la telemetría es JSONL de solo añadir,
        `app.storage.telemetry_log`, y es la misma función)."""
        return current_role(value)


class TelemetryLog(_Model):
    """Telemetría de un proyecto (en disco, `{id}/costes_telemetria.jsonl`: un registro por
    línea; ver `app.storage.telemetry_log`)."""

    schema_version: Literal[1] = 1  # formato del antiguo `.json` (solo para migrarlo)
    records: list[TelemetryRecord] = Field(default_factory=list)
