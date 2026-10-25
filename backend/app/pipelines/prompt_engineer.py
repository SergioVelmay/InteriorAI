"""PROMPT_ENGINEER: descripción + imagen base + fichas de referencias → brief de diseño."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import ValidationError

from app.foundry import FoundryClient, InputImage, TextRequest
from app.pipelines.errors import PipelineError, PipelineInputError
from app.pipelines.images import VISION_MIME_TYPES, prepare_image
from app.pipelines.prompts import load_prompt
from app.pipelines.schemas import strict_schema
from app.pipelines.sources import active_references, brief_images
from app.storage import ProjectRepository
from app.telemetry import current_request_id
from shared.models import (
    LEGACY_KIND_LABELS,
    RECIPE_GROUPS,
    Asset,
    AssetKind,
    DesignBrief,
    DesignBriefContent,
    ProjectMetadata,
    RecipeElement,
)
from shared.roles import Role

MAX_SOURCE_IMAGES = 4
MAX_OUTPUT_TOKENS = 6_000  # incluye el razonamiento del despliegue
SCHEMA = strict_schema(DesignBriefContent)


@dataclass
class BriefContext:
    text: str
    images: list[InputImage] = field(default_factory=list)
    source_ids: list[UUID] = field(default_factory=list)
    reference_ids: list[UUID] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _project_section(project: ProjectMetadata) -> str:
    return f"- Nombre: {project.name}"


def _element(element: RecipeElement) -> dict:
    entry: dict = {"elemento": element.label}
    if element.detail:
        entry["detalle"] = element.detail
    if element.dimensions_source != "ninguna":
        entry["medidas_cm"] = element.dimensions_cm.model_dump(mode="json")
        entry["origen_medidas"] = element.dimensions_source  # «estimada» = aproximada
    return entry


def _reference_entry(asset: Asset, image_number: int | None) -> dict:
    """Lo que el usuario ha marcado en la ficha de una referencia activa (B-030)."""
    sheet = asset.sheet
    entry: dict = {"id": str(asset.id), "archivo": asset.original_name}
    if image_number is not None:
        entry["imagen_adjunta"] = image_number
    if asset.description:
        entry["notas_usuario"] = asset.description
    if sheet is not None:
        entry["resumen"] = sheet.recipe.summary
        entry["seleccion"] = {
            RECIPE_GROUPS[group]: [_element(e) for e in elements]
            for group, elements in sheet.selected_elements().items()
        }
    return entry


async def build_context(
    repo: ProjectRepository,
    project: ProjectMetadata,
    instructions: str,
    parent: DesignBrief | None,
) -> BriefContext:
    warnings: list[str] = []
    sources = brief_images(project)  # imágenes del espacio (ver `sources`)
    for asset in sources:
        if asset.mime_type not in VISION_MIME_TYPES:
            warnings.append(f"'{asset.original_name}' no es una imagen y no se envía")
    usable = [a for a in sources if a.mime_type in VISION_MIME_TYPES]
    if len(usable) > MAX_SOURCE_IMAGES:
        warnings.append(
            f"Se envían las {MAX_SOURCE_IMAGES} primeras imágenes de {len(usable)} "
            "(las de perspectiva primero)"
        )
        usable = usable[:MAX_SOURCE_IMAGES]

    # Fichas: lo marcado en las referencias activas; las inactivas no se usan (B-030).
    references = active_references(project)
    for asset in project.assets:
        if asset.kind is AssetKind.REFERENCIA and asset.sheet is None:
            warnings.append(f"La referencia '{asset.original_name}' aún no está analizada")

    if not usable and not references and not project.description.strip():
        raise PipelineInputError("Añade una descripción del proyecto o imágenes de referencia")

    images = [await prepare_image(await repo.read_asset_bytes(project.id, a.id)) for a in usable]
    numbers = {a.id: i for i, a in enumerate(usable, start=1)}
    image_list = "\n".join(
        f"- Imagen {i}: {LEGACY_KIND_LABELS.get(a.legacy_kind or '', a.kind.label)} "
        f"'{a.original_name}'" + (f" — nota: {a.description}" if a.description else "")
        for i, a in enumerate(usable, start=1)
    )
    sections = [
        "## Proyecto",
        _project_section(project),
        "## Descripción del proyecto (escrita por el usuario)",
        project.description.strip() or "(sin descripción)",
        "## Imágenes adjuntas (en este orden)",
        image_list or "(ninguna)",
        "## Fichas de las referencias",
        json.dumps(
            [_reference_entry(a, numbers.get(a.id)) for a in references],
            ensure_ascii=False,
            indent=2,
        )
        if references
        else "(ninguna)",
        "## Indicaciones del usuario para esta versión",
        instructions.strip() or "(ninguna)",
    ]
    if parent is not None:
        sections += [
            f"## Versión anterior (v{parent.version}) rechazada por el usuario",
            json.dumps(parent.content.model_dump(mode="json"), ensure_ascii=False, indent=2),
            "## Comentarios del usuario sobre la versión anterior",
            parent.feedback or "(sin comentarios)",
        ]
    return BriefContext(
        text="\n\n".join(sections),
        images=images,
        source_ids=[a.id for a in usable],
        reference_ids=[a.id for a in references],
        warnings=warnings,
    )


def _sanitize(
    content: DesignBriefContent, valid_ids: set[str], warnings: list[str]
) -> DesignBriefContent:
    furniture = []
    for item in content.furniture:
        if item.reference_asset_id is not None and item.reference_asset_id not in valid_ids:
            warnings.append(f"Se descartó un id de referencia inexistente en '{item.name}'")
            item = item.model_copy(update={"reference_asset_id": None})
        furniture.append(item)
    return content.model_copy(update={"furniture": furniture})


async def create_brief(
    repo: ProjectRepository,
    client: FoundryClient,
    project_id: UUID,
    instructions: str = "",
    parent: DesignBrief | None = None,
) -> DesignBrief:
    """Genera una nueva versión del brief en estado `propuesto`."""
    project = await repo.get(project_id)
    prompt = load_prompt("prompt_engineer")
    context = await build_context(repo, project, instructions, parent)

    result = await client.complete_text(
        Role.PROMPT_ENGINEER,
        TextRequest(
            instructions=prompt.text,
            input=context.text,
            images=context.images,
            json_schema=SCHEMA,
            schema_name="brief_diseno",
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )
    try:
        content = DesignBriefContent.model_validate(result.data)
    except ValidationError as exc:
        raise PipelineError("El brief devuelto por el modelo no cumple el esquema") from exc
    content = _sanitize(content, {str(i) for i in context.reference_ids}, context.warnings)

    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, DesignBrief]:
        version = max((b.version for b in metadata.briefs), default=0) + 1
        brief = DesignBrief(
            version=version,
            content=content,
            instructions=instructions.strip(),
            parent_id=parent.id if parent else None,
            source_asset_ids=context.source_ids,
            reference_asset_ids=context.reference_ids,
            warnings=context.warnings,
            prompt_version=prompt.version,
            request_id=current_request_id(),
        )
        return metadata.model_copy(update={"briefs": [*metadata.briefs, brief]}), brief

    return await repo.mutate(project_id, change)
