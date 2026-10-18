"""Pipelines de imagen: boceto → composición → render final, a partir del brief aprobado.

Cada etapa exige como entrada un render `seleccionado` por el usuario en la etapa anterior.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from PIL import Image

from app.foundry import FoundryClient, ImageEditRequest, ImageResult, InputImage
from app.hitl import TransitionError, ensure_transition
from app.hitl.briefs import BriefNotFoundError
from app.pipelines.errors import PipelineInputError
from app.pipelines.images import VISION_MIME_TYPES, prepare_image
from app.storage import ProjectRepository
from app.telemetry import current_request_id
from shared.models import (
    Asset,
    AssetKind,
    BriefStatus,
    DesignBrief,
    ProjectMetadata,
    RenderRecord,
    RenderStage,
    RenderStatus,
    utc_now,
)
from shared.roles import Role

INPUT_MAX_SIDE_PX = 2_048  # imágenes de entrada a los modelos de imagen
MAX_RENDERER_REFERENCES = 7  # el renderizador admite 8 imágenes: composición + 7 referencias
GPT_IMAGE_SIZES = frozenset({"1024x1024", "1536x1024", "1024x1536"})
RENDERER_MAX_PIXELS = 4_000_000  # 4 MP
_SIZE = re.compile(r"^(\d{3,4})x(\d{3,4})$")

Quality = Literal["low", "medium", "high", "auto"]

RENDER_TRANSITIONS = {
    RenderStatus.GENERATED: frozenset({RenderStatus.SELECTED, RenderStatus.DISCARDED}),
    RenderStatus.SELECTED: frozenset({RenderStatus.DISCARDED}),
    RenderStatus.DISCARDED: frozenset({RenderStatus.SELECTED}),
}


class RenderNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class RenderOptions:
    n: int = 1
    size: str | None = None
    quality: Quality | None = None
    brief_id: UUID | None = None
    prompt_override: str | None = None
    extra_instructions: str = ""
    seed: int | None = None


# --- Selección de entradas -------------------------------------------------------------


def approved_brief(project: ProjectMetadata, brief_id: UUID | None) -> DesignBrief:
    if brief_id is None:
        brief = next((b for b in project.briefs if b.status is BriefStatus.APPROVED), None)
        if brief is None:
            raise TransitionError(
                "No hay ningún brief aprobado: aprueba uno antes de generar imágenes"
            )
        return brief
    brief = next((b for b in project.briefs if b.id == brief_id), None)
    if brief is None:
        raise BriefNotFoundError(str(brief_id))
    if brief.status is not BriefStatus.APPROVED:
        raise TransitionError(f"El brief v{brief.version} no está aprobado ('{brief.status}')")
    return brief


def base_asset(project: ProjectMetadata, brief: DesignBrief) -> Asset:
    """Imagen base: la primera captura/plano en imagen del brief (o del proyecto)."""
    by_id = {a.id: a for a in project.assets}
    candidates = [by_id[i] for i in brief.source_asset_ids if i in by_id]
    candidates += sorted(
        (a for a in project.assets if a.kind in {AssetKind.CAPTURA_SKETCHUP, AssetKind.PLANO}),
        key=lambda a: (a.kind is not AssetKind.CAPTURA_SKETCHUP, a.created_at),
    )
    for asset in candidates:
        if asset.mime_type in VISION_MIME_TYPES:
            return asset
    raise PipelineInputError("Sube una captura de SketchUp o un plano en imagen como base")


def selected_render(project: ProjectMetadata, render_id: UUID, stage: RenderStage) -> RenderRecord:
    render = next((r for r in project.renders if r.id == render_id), None)
    if render is None:
        raise RenderNotFoundError(str(render_id))
    if render.stage is not stage:
        raise PipelineInputError(f"El render {render_id} no es de la etapa '{stage.label}'")
    if render.status is not RenderStatus.SELECTED:
        raise TransitionError(
            f"El render {render_id} está '{render.status}': selecciónalo antes de usarlo"
        )
    return render


# --- Tamaños -----------------------------------------------------------------------------


def _orientation(asset: Asset) -> str:
    if not asset.width_px or not asset.height_px or asset.width_px == asset.height_px:
        return "square"
    return "landscape" if asset.width_px > asset.height_px else "portrait"


_DEFAULT_SIZES = {
    "gpt": {"landscape": "1536x1024", "portrait": "1024x1536", "square": "1024x1024"},
    "renderer": {"landscape": "1920x1280", "portrait": "1280x1920", "square": "1536x1536"},
}


def resolve_size(role: Role, requested: str | None, base: Asset) -> str:
    family = "renderer" if role is Role.PHOTOREALISTIC_RENDERER else "gpt"
    size = requested or _DEFAULT_SIZES[family][_orientation(base)]
    if family == "gpt":
        if size not in GPT_IMAGE_SIZES:
            raise PipelineInputError(
                f"Tamaño no admitido para {role.value}: usa {', '.join(sorted(GPT_IMAGE_SIZES))}"
            )
        return size
    match = _SIZE.fullmatch(size)
    if not match:
        raise PipelineInputError("El tamaño debe tener el formato <ancho>x<alto>")
    width, height = int(match[1]), int(match[2])
    if width % 16 or height % 16 or width * height > RENDERER_MAX_PIXELS:
        raise PipelineInputError(
            "Para el render final, ancho y alto múltiplos de 16 y como máximo 4 MP"
        )
    return size


# --- Ejecución -----------------------------------------------------------------------------


def build_prompt(base_prompt: str, options: RenderOptions) -> str:
    prompt = (options.prompt_override or base_prompt).strip()
    if options.extra_instructions.strip():
        prompt = f"{prompt}\n\n{options.extra_instructions.strip()}"
    return prompt


async def _load(repo: ProjectRepository, project: ProjectMetadata, asset_id: UUID) -> InputImage:
    return await prepare_image(await repo.read_asset_bytes(project.id, asset_id), INPUT_MAX_SIDE_PX)


def _size_of(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size


async def _run_stage(
    repo: ProjectRepository,
    client: FoundryClient,
    project: ProjectMetadata,
    brief: DesignBrief,
    stage: RenderStage,
    role: Role,
    inputs: list[UUID],
    parent: RenderRecord | None,
    base_prompt: str,
    options: RenderOptions,
    output_format: Literal["png", "jpeg"],
) -> list[RenderRecord]:
    base = next(a for a in project.assets if a.id == inputs[0])
    size = resolve_size(role, options.size, base)
    images = [await _load(repo, project, asset_id) for asset_id in inputs]
    prompt = build_prompt(base_prompt, options)
    quality = options.quality or "auto"
    result: ImageResult = await client.edit_image(
        role,
        ImageEditRequest(
            prompt=prompt,
            size=size,
            n=options.n,
            quality=quality,
            output_format=output_format,
            seed=options.seed,
            images=images,
        ),
    )

    estimate = getattr(client, "estimate", None)
    deployment_name = getattr(client, "deployment_name", None)
    references = [_size_of(img.data) for img in images]
    total = (
        estimate(role, result.usage, [(i.width, i.height) for i in result.images], references)
        if estimate
        else None
    )
    batch_id = uuid4()
    records = []
    for generated in result.images:
        record = RenderRecord(
            id=uuid4(),
            stage=stage,
            role=role,
            deployment=deployment_name(role) if deployment_name else result.deployment,
            brief_id=brief.id,
            brief_version=brief.version,
            prompt=prompt,
            input_asset_ids=inputs,
            parent_render_id=parent.id if parent else None,
            batch_id=batch_id,
            size=size,
            quality=None if role is Role.PHOTOREALISTIC_RENDERER else quality,
            seed=options.seed,
            request_id=current_request_id(),
            cost_eur=round(total / len(result.images), 6) if total is not None else None,
        )
        await repo.add_render(
            project.id,
            record,
            generated.data,
            generated.mime_type,
            generated.width,
            generated.height,
        )
        records.append(record)
    return records


async def generate_drafts(
    repo: ProjectRepository, client: FoundryClient, project_id: UUID, options: RenderOptions
) -> list[RenderRecord]:
    """Etapa 1: bocetos a partir de la captura de SketchUp (imagen base)."""
    project = await repo.get(project_id)
    brief = approved_brief(project, options.brief_id)
    base = base_asset(project, brief)
    return await _run_stage(
        repo, client, project, brief, RenderStage.DRAFT, Role.FAST_DRAFT, [base.id], None,
        brief.content.image_prompts.fast_draft,
        RenderOptions(**{**options.__dict__, "quality": options.quality or "low"}), "png",
    )  # fmt: skip


async def generate_composition(
    repo: ProjectRepository,
    client: FoundryClient,
    project_id: UUID,
    options: RenderOptions,
    draft_id: UUID | None = None,
) -> list[RenderRecord]:
    """Etapa 2: composición sobre la captura; el boceto seleccionado aporta color y ambiente."""
    project = await repo.get(project_id)
    brief = approved_brief(project, options.brief_id)
    base = base_asset(project, brief)
    draft = selected_render(project, draft_id, RenderStage.DRAFT) if draft_id else None
    inputs = [base.id] + ([draft.id] if draft else [])
    return await _run_stage(
        repo, client, project, brief, RenderStage.COMPOSITION, Role.STRUCTURAL_COMPOSER, inputs,
        draft, brief.content.image_prompts.structural_composer,
        RenderOptions(**{**options.__dict__, "quality": options.quality or "medium"}), "png",
    )  # fmt: skip


async def generate_final(
    repo: ProjectRepository,
    client: FoundryClient,
    project_id: UUID,
    options: RenderOptions,
    composition_id: UUID,
    reference_ids: list[UUID] | None = None,
) -> list[RenderRecord]:
    """Etapa 3: render fotorrealista con la composición seleccionada y referencias."""
    project = await repo.get(project_id)
    composition = selected_render(project, composition_id, RenderStage.COMPOSITION)
    brief = approved_brief(project, options.brief_id or composition.brief_id)
    references_by_id = {
        a.id: a
        for a in project.assets
        if a.kind is AssetKind.REFERENCIA and a.mime_type in VISION_MIME_TYPES
    }
    wanted = brief.reference_asset_ids if reference_ids is None else reference_ids
    unknown = [str(i) for i in wanted if i not in references_by_id]
    if unknown and reference_ids is not None:
        raise PipelineInputError("No son referencias en imagen del proyecto: " + ", ".join(unknown))
    references = [i for i in wanted if i in references_by_id][:MAX_RENDERER_REFERENCES]
    return await _run_stage(
        repo, client, project, brief, RenderStage.FINAL, Role.PHOTOREALISTIC_RENDERER,
        [composition.id, *references], composition,
        brief.content.image_prompts.photorealistic_renderer, options, "jpeg",
    )  # fmt: skip


async def decide_render(
    repo: ProjectRepository, project_id: UUID, render_id: UUID, target: RenderStatus
) -> RenderRecord:
    """Selección o descarte de un render por el usuario."""

    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, RenderRecord]:
        renders = list(metadata.renders)
        for i, render in enumerate(renders):
            if render.id == render_id:
                ensure_transition(RENDER_TRANSITIONS, render.status, target, "el render")
                renders[i] = render.model_copy(update={"status": target, "decided_at": utc_now()})
                return metadata.model_copy(update={"renders": renders}), renders[i]
        raise RenderNotFoundError(str(render_id))

    return await repo.mutate(project_id, change)
