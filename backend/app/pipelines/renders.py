"""Pipelines de imagen: boceto → composición → render final, a partir del brief aprobado.

Cada etapa exige como entrada un render `seleccionado` por el usuario en la etapa anterior.
Las composiciones y los renders finales admiten retoques de una zona (`inpaint_render`).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

import anyio
from PIL import Image

from app.foundry import FoundryClient, ImageEditRequest, ImageResult, InputImage
from app.hitl import TransitionError, ensure_transition
from app.hitl.briefs import BriefNotFoundError
from app.pipelines import masks
from app.pipelines.errors import PipelineInputError
from app.pipelines.images import VISION_MIME_TYPES, prepare_image
from app.pipelines.sources import base_candidates
from app.storage import ProjectRepository
from app.telemetry import current_request_id
from shared.models import (
    Asset,
    AssetKind,
    BriefStatus,
    DesignBrief,
    ProjectMetadata,
    RenderInpaint,
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
RENDERER_LONG_SIDE_PX = 1_920
INPAINT_STAGES = frozenset({RenderStage.COMPOSITION, RenderStage.FINAL})
_SIZE = re.compile(r"^(\d{3,4})x(\d{3,4})$")

Quality = Literal["low", "medium", "high", "auto"]

RENDER_TRANSITIONS = {
    RenderStatus.GENERATED: frozenset(
        {RenderStatus.SELECTED, RenderStatus.DISCARDED, RenderStatus.REJECTED}
    ),
    RenderStatus.SELECTED: frozenset({RenderStatus.DISCARDED, RenderStatus.REJECTED}),
    RenderStatus.DISCARDED: frozenset({RenderStatus.SELECTED, RenderStatus.REJECTED}),
    # REJECTED es terminal: se sustituye por una nueva imagen (previous_attempt_id)
}

# Rol y formato de salida de cada etapa. Todo en PNG (sin pérdida): el render final también,
# a petición del usuario (Paso 10); el renderizador cobra por MP, no por formato.
_STAGE_ROLES: dict[RenderStage, tuple[Role, Literal["png", "jpeg"]]] = {
    RenderStage.DRAFT: (Role.FAST_DRAFT, "png"),
    RenderStage.COMPOSITION: (Role.STRUCTURAL_COMPOSER, "png"),
    RenderStage.FINAL: (Role.PHOTOREALISTIC_RENDERER, "png"),
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
    """Imagen base: la primera imagen base del brief o, si no, la del proyecto (`sources`)."""
    by_id = {a.id: a for a in project.assets}
    candidates = [by_id[i] for i in brief.source_asset_ids if i in by_id]
    for asset in [*candidates, *base_candidates(project)]:
        if asset.mime_type in VISION_MIME_TYPES:
            return asset
    raise PipelineInputError("Sube una imagen del espacio (p. ej. una captura de SketchUp)")


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


def _orientation_of(width: int | None, height: int | None) -> str:
    if not width or not height or width == height:
        return "square"
    return "landscape" if width > height else "portrait"


def _orientation(asset: Asset) -> str:
    return _orientation_of(asset.width_px, asset.height_px)


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
    api_width, api_height = _ceil16(width), _ceil16(height)
    if min(width, height) < 256 or api_width * api_height > RENDERER_MAX_PIXELS:
        raise PipelineInputError("Para el render final, lado mínimo de 256 px y como máximo 4 MP")
    return size


def _ceil16(value: int) -> int:
    return -(-value // 16) * 16


def generation_size(role: Role, size: str) -> str:
    """Tamaño que se pide al modelo para entregar `size`. El renderizador trabaja en múltiplos
    de 16 px: se pide el múltiplo superior (1920x1080 → 1920x1088) y después se recorta al
    centro hasta el tamaño exacto, sin escalar (`masks.fit`).

    Comprobado con una llamada real (B-020, Paso 16): si se le pide 1920x1080, lo acepta pero
    devuelve 1920x1072 (redondea hacia abajo en silencio), así que no basta con pedir el
    tamaño exacto."""
    if role is not Role.PHOTOREALISTIC_RENDERER:
        return size
    width, height = (int(v) for v in size.split("x"))
    return f"{_ceil16(width)}x{_ceil16(height)}"


def renderer_size(capture: Asset) -> str | None:
    """Tamaño del render final con la proporción exacta de la captura (B-018): lado largo de
    1920 px (16:9 → 1920x1080). None si no se conocen sus medidas."""
    width, height = capture.width_px, capture.height_px
    if not width or not height:
        return None
    if width == height:
        return _DEFAULT_SIZES["renderer"]["square"]
    short = round(RENDERER_LONG_SIDE_PX * min(width, height) / max(width, height))
    if width > height:
        return f"{RENDERER_LONG_SIDE_PX}x{short}"
    return f"{short}x{RENDERER_LONG_SIDE_PX}"


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


def _call_cost(
    client: FoundryClient, role: Role, result: ImageResult, images: list[InputImage]
) -> float | None:
    """Coste estimado de la llamada (None si el cliente no lleva telemetría de precios)."""
    estimate = getattr(client, "estimate", None)
    if estimate is None:
        return None
    outputs = [(i.width, i.height) for i in result.images]
    return estimate(role, result.usage, outputs, [_size_of(img.data) for img in images])


def _deployment(client: FoundryClient, role: Role, result: ImageResult) -> str:
    deployment_name = getattr(client, "deployment_name", None)
    return deployment_name(role) if deployment_name else result.deployment


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
    *,
    previous_attempt_id: UUID | None = None,
) -> list[RenderRecord]:
    # La imagen base es la primera entrada (asset subido o render de la etapa anterior).
    base = next(a for a in project.assets if a.id == inputs[0])
    size = resolve_size(role, options.size, base)
    images = [await _load(repo, project, asset_id) for asset_id in inputs]
    prompt = build_prompt(base_prompt, options)
    quality = options.quality or "auto"
    result: ImageResult = await client.edit_image(
        role,
        ImageEditRequest(
            prompt=prompt,
            size=generation_size(role, size),
            n=options.n,
            quality=quality,
            output_format=output_format,
            seed=options.seed,
            images=images,
        ),
    )

    total = _call_cost(client, role, result, images)  # por lo generado (antes de recortar)
    target = tuple(int(v) for v in size.split("x"))
    batch_id = uuid4()
    records = []
    for generated in result.images:
        content = await anyio.to_thread.run_sync(masks.fit_png, generated.data, target)
        record = RenderRecord(
            id=uuid4(),
            stage=stage,
            role=role,
            deployment=_deployment(client, role, result),
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
            previous_attempt_id=previous_attempt_id,
        )
        mime = generated.mime_type if content is generated.data else "image/png"
        await repo.add_render(project.id, record, content, mime, target[0], target[1])
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
        RenderOptions(**{**options.__dict__, "quality": options.quality or "low"}),
        _STAGE_ROLES[RenderStage.DRAFT][1],
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
        RenderOptions(**{**options.__dict__, "quality": options.quality or "medium"}),
        _STAGE_ROLES[RenderStage.COMPOSITION][1],
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
        if a.kind is AssetKind.REFERENCIA
        and a.legacy_kind is None  # capturas y planos de la v1: no son texturas (B-028)
        and a.mime_type in VISION_MIME_TYPES
    }
    wanted = brief.reference_asset_ids if reference_ids is None else reference_ids
    unknown = [str(i) for i in wanted if i not in references_by_id]
    if unknown and reference_ids is not None:
        raise PipelineInputError("No son referencias en imagen del proyecto: " + ", ".join(unknown))
    references = [i for i in wanted if i in references_by_id][:MAX_RENDERER_REFERENCES]
    # Por defecto, la proporción de la captura original, no la de la composición (3:2).
    size = options.size or renderer_size(base_asset(project, brief))
    return await _run_stage(
        repo, client, project, brief, RenderStage.FINAL, Role.PHOTOREALISTIC_RENDERER,
        [composition.id, *references], composition,
        brief.content.image_prompts.photorealistic_renderer,
        RenderOptions(**{**options.__dict__, "size": size}),
        _STAGE_ROLES[RenderStage.FINAL][1],
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
                now = utc_now()
                renders[i] = render.model_copy(update={"status": target, "decided_at": now})
                if target is RenderStatus.SELECTED and render.stage is RenderStage.FINAL:
                    # Un único render final seleccionado: el anterior pasa a descartado.
                    for j, other in enumerate(renders):
                        if (
                            j != i
                            and other.stage is RenderStage.FINAL
                            and (other.status is RenderStatus.SELECTED)
                        ):
                            renders[j] = other.model_copy(
                                update={"status": RenderStatus.DISCARDED, "decided_at": now}
                            )
                return metadata.model_copy(update={"renders": renders}), renders[i]
        raise RenderNotFoundError(str(render_id))

    return await repo.mutate(project_id, change)


def feedback_prompt(render: RenderRecord, feedback: str, audit_suggestions: str | None) -> str:
    """Prompt anterior + comentarios del usuario (+ correcciones del auditor, si se aplican)."""
    parts = [render.prompt, f"User feedback (in Spanish, apply it): {feedback.strip()}"]
    if audit_suggestions and audit_suggestions.strip():
        parts.append(f"Corrections from the geometric audit: {audit_suggestions.strip()}")
    return "\n\n".join(parts)


async def reject_render(
    repo: ProjectRepository,
    client: FoundryClient,
    project_id: UUID,
    render_id: UUID,
    feedback: str,
    regenerate: bool = True,
    apply_audit_suggestions: bool = True,
) -> tuple[RenderRecord, list[RenderRecord]]:
    """Rechazo con comentarios; si `regenerate`, nueva imagen de la misma etapa y entradas."""

    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, RenderRecord]:
        renders = list(metadata.renders)
        for i, render in enumerate(renders):
            if render.id == render_id:
                ensure_transition(
                    RENDER_TRANSITIONS, render.status, RenderStatus.REJECTED, "el render"
                )
                renders[i] = render.model_copy(
                    update={
                        "status": RenderStatus.REJECTED,
                        "feedback": feedback.strip(),
                        "decided_at": utc_now(),
                    }
                )
                return metadata.model_copy(update={"renders": renders}), renders[i]
        raise RenderNotFoundError(str(render_id))

    rejected = await repo.mutate(project_id, change)
    if not regenerate:
        return rejected, []
    retouch = rejected
    if rejected.raw_of_render_id is not None:  # salida en bruto: se repite su retoque
        project = await repo.get(project_id)
        retouch = next((r for r in project.renders if r.id == rejected.raw_of_render_id), rejected)
    if retouch.inpaint is not None:
        # Un retoque se repite sobre la misma imagen y con la misma máscara.
        mask = await repo.read_render_file(project_id, retouch.inpaint.mask_file)
        instruction = (
            f"{retouch.inpaint.instruction}\n\n"
            f"Feedback on the previous attempt (in Spanish): {feedback.strip()}"
        )
        new = await inpaint_render(
            repo, client, project_id, retouch.inpaint.source_render_id, mask, instruction,
            quality=rejected.quality, previous_attempt_id=rejected.id,  # type: ignore[arg-type]
        )  # fmt: skip
        return rejected, [new]

    project = await repo.get(project_id)
    brief = next((b for b in project.briefs if b.id == rejected.brief_id), None)
    if brief is None:
        raise BriefNotFoundError(str(rejected.brief_id))
    parent = next((r for r in project.renders if r.id == rejected.parent_render_id), None)
    suggestions = (
        rejected.audits[-1].report.suggested_prompt_adjustments
        if apply_audit_suggestions and rejected.audits
        else None
    )
    role, output_format = _STAGE_ROLES[rejected.stage]
    options = RenderOptions(
        n=1,
        size=rejected.size,
        quality=rejected.quality,  # type: ignore[arg-type]
        seed=rejected.seed,
        prompt_override=feedback_prompt(rejected, feedback, suggestions),
    )
    new = await _run_stage(
        repo, client, project, brief, rejected.stage, role, rejected.input_asset_ids, parent,
        rejected.prompt, options, output_format, previous_attempt_id=rejected.id,
    )  # fmt: skip
    return rejected, new


# --- Retoque de una zona (inpainting, Paso 13b) ---------------------------------------------


def inpaint_prompt(instruction: str, method: str, bounds: str) -> str:
    """Prompt del retoque. Lo que se añada debe caber entero en la zona: fuera de ella se
    descarta al recomponer, y un objeto que se salga quedaría cortado por el borde."""
    change = instruction.strip()
    keep = "same framing, geometry, perspective, camera, lighting, materials and colors"
    contain = (
        f"The area spans {bounds}. Everything you add or change must fit entirely inside "
        "that area, with a clear margin to its edges: nothing new may cross or touch them."
    )
    if method == "mascara":
        return (
            "Edit only the transparent area of the mask. Requested change (in Spanish, apply "
            f"it): {change}\n\n{contain}\n\nKeep everything else exactly as it is: {keep}. "
            "Blend the edit seamlessly with its surroundings."
        )
    return (
        "Image 1 is the photo to edit. Image 2 is the same photo with the area to change "
        "highlighted in red. Apply this change only inside that area (in Spanish): "
        f"{change}\n\n{contain}\n\nReproduce the rest of image 1 exactly: {keep}. "
        "Do not draw the red highlight."
    )


async def inpaint_render(
    repo: ProjectRepository,
    client: FoundryClient,
    project_id: UUID,
    render_id: UUID,
    mask_data: bytes,
    instruction: str,
    *,
    quality: Quality | None = None,
    previous_attempt_id: UUID | None = None,
) -> RenderRecord:
    """Retoca la zona pintada de una composición o render final.

    Composición: edición con máscara nativa (STRUCTURAL_COMPOSER). Render final: el renderizador
    no admite máscara, así que regenera la imagen completa con una guía de la zona. En ambos
    casos solo se conserva la zona pintada (recomposición local exacta, B-009): la imagen
    original no cambia y el retoque es una imagen nueva de la misma etapa, sin seleccionar.
    """
    if not instruction.strip():
        raise PipelineInputError("Describe el cambio que quieres en la zona pintada")
    project = await repo.get(project_id)
    source = next((r for r in project.renders if r.id == render_id), None)
    if source is None:
        raise RenderNotFoundError(str(render_id))
    if source.stage not in INPAINT_STAGES:
        raise PipelineInputError("Solo se pueden retocar composiciones y renders finales")

    source_data = await repo.read_asset_bytes(project.id, source.id)
    width, height = _size_of(source_data)
    zone = await anyio.to_thread.run_sync(masks.edit_zone, mask_data, (width, height))
    covered = masks.check_coverage(zone)
    role, output_format = _STAGE_ROLES[source.stage]
    source_image = await prepare_image(source_data, INPUT_MAX_SIDE_PX)
    bounds = masks.zone_bounds_text(zone)
    guide: bytes | None = None

    if role is Role.PHOTOREALISTIC_RENDERER:
        method, quality_used = "regeneracion", None
        guide = await anyio.to_thread.run_sync(masks.guide_image, source_data, zone)
        images = [source_image, InputImage(data=guide, mime_type="image/jpeg")]
        request = ImageEditRequest(
            prompt=inpaint_prompt(instruction, method, bounds),
            size=generation_size(role, f"{width}x{height}"),
            output_format=output_format, images=images,
        )  # fmt: skip
    else:
        method, quality_used = "mascara", quality or source.quality or "medium"
        size = f"{width}x{height}"
        if size not in GPT_IMAGE_SIZES:
            size = _DEFAULT_SIZES["gpt"][_orientation_of(width, height)]
        model_mask = await anyio.to_thread.run_sync(
            masks.model_mask, zone, _size_of(source_image.data)
        )
        images = [source_image]
        request = ImageEditRequest(
            prompt=inpaint_prompt(instruction, method, bounds), size=size,
            quality=quality_used,
            output_format=output_format, images=images,
            mask=InputImage(data=model_mask, mime_type="image/png"),
        )  # fmt: skip

    result = await client.edit_image(role, request)
    raw = result.images[0]
    content = await anyio.to_thread.run_sync(
        masks.recompose, source_data, raw.data, zone, masks.FEATHER_PX
    )
    total = _call_cost(client, role, result, images)
    record_id = uuid4()
    raw_ext = "jpeg" if raw.mime_type == "image/jpeg" else "png"
    files = {
        f"{record_id}-mascara.png": await anyio.to_thread.run_sync(masks.zone_png, zone),
        f"{record_id}-bruto.{raw_ext}": raw.data,  # para comparar con la recomposición
    }
    if guide is not None:
        files[f"{record_id}-guia.jpeg"] = guide
    record = RenderRecord(
        id=record_id,
        stage=source.stage,
        role=role,
        deployment=_deployment(client, role, result),
        brief_id=source.brief_id,
        brief_version=source.brief_version,
        prompt=request.prompt,
        input_asset_ids=[source.id],
        parent_render_id=source.parent_render_id,
        batch_id=uuid4(),
        size=f"{width}x{height}",
        quality=quality_used,
        request_id=current_request_id(),
        cost_eur=round(total, 6) if total is not None else None,
        previous_attempt_id=previous_attempt_id,
        inpaint=RenderInpaint(
            source_render_id=source.id,
            instruction=instruction.strip(),
            mask_file=f"{record_id}-mascara.png",
            raw_file=f"{record_id}-bruto.{raw_ext}",
            guide_file=f"{record_id}-guia.jpeg" if guide is not None else None,
            coverage=covered,
            feather_px=masks.FEATHER_PX,
            method=method,
        ),
    )
    await repo.add_render(project.id, record, content, "image/png", width, height, sidecars=files)
    return record


async def use_raw_output(
    repo: ProjectRepository, project_id: UUID, render_id: UUID
) -> RenderRecord:
    """Guarda la salida en bruto de un retoque (la imagen completa que generó el modelo, sin
    recomponer) como imagen nueva de la misma etapa. Sin coste: la llamada ya se pagó."""
    project = await repo.get(project_id)
    retouch = next((r for r in project.renders if r.id == render_id), None)
    if retouch is None:
        raise RenderNotFoundError(str(render_id))
    if retouch.inpaint is None or retouch.inpaint.raw_file is None:
        raise PipelineInputError("Esta imagen no es un retoque con salida en bruto guardada")
    if any(r.raw_of_render_id == retouch.id for r in project.renders):
        raise TransitionError("La salida en bruto de este retoque ya es una imagen del proyecto")
    content = await repo.read_render_file(project_id, retouch.inpaint.raw_file)
    # La salida en bruto puede venir en múltiplos de 16 (1920x1088): se entrega al tamaño exacto.
    width, height = (int(v) for v in retouch.size.split("x"))
    content = await anyio.to_thread.run_sync(masks.fit_png, content, (width, height))
    record = retouch.model_copy(
        update={
            "id": uuid4(),
            "status": RenderStatus.GENERATED,
            "size": f"{width}x{height}",
            "cost_eur": 0.0,  # ya contado en el retoque
            "audits": [],
            "feedback": None,
            "previous_attempt_id": None,
            "inpaint": None,
            "raw_of_render_id": retouch.id,
            "created_at": utc_now(),
            "decided_at": None,
        }
    )
    mime = "image/jpeg" if content[:3] == b"\xff\xd8\xff" else "image/png"
    await repo.add_render(project.id, record, content, mime, width, height)
    return record
