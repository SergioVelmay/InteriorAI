"""PROMPT_ENGINEER: notas + planos/capturas + fichas de referencias → brief de diseño."""

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
from app.storage import ProjectRepository
from shared.models import (
    Asset,
    AssetKind,
    DesignBrief,
    DesignBriefContent,
    ProjectMetadata,
)
from shared.roles import Role

MAX_SOURCE_IMAGES = 4
MAX_OUTPUT_TOKENS = 6_000  # incluye el razonamiento del despliegue
SCHEMA = strict_schema(DesignBriefContent)
_SOURCE_ORDER = {AssetKind.CAPTURA_SKETCHUP: 0, AssetKind.PLANO: 1}


@dataclass
class BriefContext:
    text: str
    images: list[InputImage] = field(default_factory=list)
    source_ids: list[UUID] = field(default_factory=list)
    reference_ids: list[UUID] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _project_section(project: ProjectMetadata) -> str:
    lines = [f"- Nombre: {project.name}", f"- Tipo de espacio: {project.space_type.label}"]
    if project.description:
        lines.append(f"- Descripción: {project.description}")
    if project.dimensions:
        d = project.dimensions
        height = f" x {d.height_m} m de alto" if d.height_m else ""
        lines.append(f"- Dimensiones: {d.width_m} x {d.length_m} m{height}")
    if project.style:
        lines.append(f"- Estilo deseado: {project.style}")
    if project.budget_eur is not None:
        lines.append(f"- Presupuesto: {project.budget_eur:.0f} EUR")
    return "\n".join(lines)


def _reference_entry(asset: Asset) -> dict:
    entry: dict = {"id": str(asset.id), "archivo": asset.original_name}
    if asset.description:
        entry["nota_usuario"] = asset.description
    if asset.analysis is not None:
        entry["estado_ficha"] = asset.analysis.status
        entry["ficha"] = asset.analysis.result.model_dump(mode="json")
    return entry


async def build_context(
    repo: ProjectRepository,
    project: ProjectMetadata,
    instructions: str,
    parent: DesignBrief | None,
) -> BriefContext:
    warnings: list[str] = []
    sources = sorted(
        (a for a in project.assets if a.kind in _SOURCE_ORDER),
        key=lambda a: (_SOURCE_ORDER[a.kind], a.created_at),
    )
    for asset in sources:
        if asset.mime_type not in VISION_MIME_TYPES:
            warnings.append(f"'{asset.original_name}' es un PDF y no se envía (solo imágenes)")
    usable = [a for a in sources if a.mime_type in VISION_MIME_TYPES]
    if len(usable) > MAX_SOURCE_IMAGES:
        warnings.append(
            f"Se envían las {MAX_SOURCE_IMAGES} primeras imágenes de {len(usable)} "
            "(capturas de SketchUp primero)"
        )
        usable = usable[:MAX_SOURCE_IMAGES]

    references = [a for a in project.assets if a.kind is AssetKind.REFERENCIA]
    for asset in references:
        if asset.analysis is None:
            warnings.append(f"La referencia '{asset.original_name}' no está indexada")

    if not usable and not references and not project.design_notes.strip():
        raise PipelineInputError(
            "Añade notas de diseño, una captura de SketchUp, un plano o referencias"
        )

    images = [await prepare_image(await repo.read_asset_bytes(project.id, a.id)) for a in usable]
    image_list = "\n".join(
        f"- Imagen {i}: {a.kind.label} '{a.original_name}'"
        + (f" — nota: {a.description}" if a.description else "")
        for i, a in enumerate(usable, start=1)
    )
    sections = [
        "## Proyecto",
        _project_section(project),
        "## Notas de diseño del usuario",
        project.design_notes.strip() or "(sin notas)",
        "## Imágenes adjuntas (en este orden)",
        image_list or "(ninguna)",
        "## Fichas de las referencias",
        json.dumps([_reference_entry(a) for a in references], ensure_ascii=False, indent=2)
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
        )
        return metadata.model_copy(update={"briefs": [*metadata.briefs, brief]}), brief

    return await repo.mutate(project_id, change)
