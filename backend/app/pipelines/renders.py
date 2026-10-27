"""Pipelines de imagen: boceto → composición → render final.

Cada etapa exige como entrada el render `seleccionado` por el usuario en la etapa anterior (uno
solo por etapa, B-043).
Las composiciones admiten retoques de una zona con máscara (`inpaint_render`, B-038).
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
from app.pipelines import masks
from app.pipelines.errors import PipelineInputError
from app.pipelines.images import VISION_MIME_TYPES, prepare_image
from app.pipelines.prompt_writer import InputRole, WrittenPrompt, write_prompt
from app.pipelines.sources import active_references, draft_base, split_supports
from app.storage import ProjectRepository
from app.telemetry import current_request_id
from shared.models import (
    Asset,
    ProjectMetadata,
    RenderInpaint,
    RenderRecord,
    RenderStage,
    RenderStatus,
    utc_now,
)
from shared.roles import Role
from shared.sizes import DEFAULT_RENDERER_SIZE

INPUT_MAX_SIDE_PX = 2_048  # imágenes de entrada a los modelos de imagen
GPT_IMAGE_SIZES = frozenset({"1024x1024", "1536x1024", "1024x1536"})
RENDERER_MAX_PIXELS = 4_000_000  # 4 MP
INPAINT_STAGES = frozenset({RenderStage.COMPOSITION})  # solo con máscara nativa (B-038)
DEFAULT_GPT_SIZE = "1536x1024"  # 3:2 (B-040)
# Papel de cada imagen de entrada, tal como se explica al PROMPT_ARCHITECT.
BASE_ROLE = "imagen base: se dibuja sobre ella y se conserva su punto de vista y su geometría"
SUPPORT_ROLE = "apoyo: se toma solo lo marcado en su ficha"
START_DRAFT_ROLE = (
    "imagen de partida: el boceto seleccionado, que se materializa con fidelidad en geometría, "
    "proporciones y mobiliario"
)
START_COMPOSITION_ROLE = (
    "imagen de partida: la composición actual, que se mejora conservando lo que no se pide cambiar"
)
RETOUCH_ROLE = "imagen que se retoca: solo la zona de la máscara (transparente)"
CompositionSource = Literal["boceto", "composicion"]
FINAL_FROM_COMPOSITION_ROLE = (
    "imagen de partida: la composición seleccionada, que se convierte en una fotografía realista "
    "conservando encuadre, geometría y mobiliario"
)
FINAL_FROM_RENDER_ROLE = (
    "imagen de partida: el render final actual, una fotografía que se mejora o cambia de forma "
    "global conservando encuadre, geometría y mobiliario"
)
FinalSource = Literal["composicion", "render_final"]
_SIZE = re.compile(r"^(\d{3,4})x(\d{3,4})$")

Quality = Literal["low", "medium", "high", "auto"]

# Solo el usuario selecciona. Una imagen seleccionada vuelve a `generado` cuando se selecciona
# otra de la misma etapa (sin rechazos ni descartes desde la v2, B-048).
RENDER_TRANSITIONS = {
    RenderStatus.GENERATED: frozenset({RenderStatus.SELECTED}),
    RenderStatus.SELECTED: frozenset({RenderStatus.GENERATED}),
}

# Rol y formato de salida de cada etapa. Todo en PNG (sin pérdida): el render final también,
# a petición del usuario (Paso 10); el renderizador cobra por MP, no por formato.
_STAGE_ROLES: dict[RenderStage, tuple[Role, Literal["png", "jpeg"]]] = {
    RenderStage.DRAFT: (Role.FAST_DRAFT_MAKER, "png"),
    RenderStage.COMPOSITION: (Role.COMPOSITION_BUILDER, "png"),
    RenderStage.FINAL: (Role.REALISTIC_RENDERER, "png"),
}


class RenderNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class RenderOptions:
    n: int = 1
    size: str | None = None
    quality: Quality | None = None
    prompt_override: str | None = None
    extra_instructions: str = ""
    seed: int | None = None


# --- Selección de entradas -------------------------------------------------------------


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
    family = "renderer" if role is Role.REALISTIC_RENDERER else "gpt"
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
    if role is not Role.REALISTIC_RENDERER:
        return size
    width, height = (int(v) for v in size.split("x"))
    return f"{_ceil16(width)}x{_ceil16(height)}"


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
    stage: RenderStage,
    inputs: list[UUID],
    parent: RenderRecord | None,
    prompt: str,
    size: str,
    options: RenderOptions,
    *,
    written: WrittenPrompt | None = None,
    variant_of: UUID | None = None,
) -> list[RenderRecord]:
    """Llama al modelo de la etapa con sus entradas (la primera, la imagen de partida) y guarda
    las imágenes con el prompt que se escribió para ellas (`written`)."""
    role, output_format = _STAGE_ROLES[stage]
    images = [await _load(repo, project, asset_id) for asset_id in inputs]
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
            prompt=prompt,
            prompt_info=written.prompt if written else None,
            prompt_version=written.version if written else None,
            input_asset_ids=inputs,
            parent_render_id=parent.id if parent else None,
            variant_of_id=variant_of,
            batch_id=batch_id,
            size=size,
            quality=None if role is Role.REALISTIC_RENDERER else quality,
            seed=options.seed,
            request_id=current_request_id(),
            cost_eur=round(total / len(result.images), 6) if total is not None else None,
        )
        mime = generated.mime_type if content is generated.data else "image/png"
        await repo.add_render(project.id, record, content, mime, target[0], target[1])
        records.append(record)
    return records


async def _prompt(
    repo: ProjectRepository,
    client: FoundryClient,
    project: ProjectMetadata,
    stage: RenderStage,
    inputs: list[InputRole],
    size: str,
    options: RenderOptions,
    extras: dict[str, str] | None = None,
) -> tuple[str, WrittenPrompt | None]:
    """El prompt de la generación: el que escribe el PROMPT_ARCHITECT con las entradas reales
    (Paso 22) o, si el usuario lo da, el suyo tal cual."""
    if options.prompt_override:
        return build_prompt(options.prompt_override, options), None
    written = await write_prompt(
        repo, client, project, stage, inputs, active_references(project),
        options.extra_instructions, size, extras,
    )  # fmt: skip
    return written.prompt.prompt, written


async def generate_drafts(
    repo: ProjectRepository, client: FoundryClient, project_id: UUID, options: RenderOptions
) -> list[RenderRecord]:
    """Etapa 1 (B-036): bocetos a partir de las referencias activas, con prompt automático.

    Si alguna referencia activa tiene la perspectiva marcada, el boceto se dibuja sobre ella; las
    demás activas van como apoyo (solo lo marcado). Sin perspectiva, el modelo compone
    libremente la estancia a partir de los apoyos.
    """
    project = await repo.get(project_id)
    active = [a for a in active_references(project) if a.mime_type in VISION_MIME_TYPES]
    if not active:
        raise PipelineInputError(
            "Activa al menos una referencia (marca algo en su ficha) para generar bocetos"
        )
    base = draft_base(project)
    supports, _ = split_supports(project, base)  # hasta MAX_SUPPORTS, por prioridad
    inputs = [InputRole(base, BASE_ROLE)] if base else []
    inputs += [InputRole(a, SUPPORT_ROLE) for a in supports]
    size = resolve_size(Role.FAST_DRAFT_MAKER, options.size or DEFAULT_GPT_SIZE, inputs[0].asset)
    options = RenderOptions(**{**options.__dict__, "quality": options.quality or "medium"})
    prompt, written = await _prompt(repo, client, project, RenderStage.DRAFT, inputs, size, options)
    return await _run_stage(
        repo, client, project, RenderStage.DRAFT, [i.asset.id for i in inputs], None, prompt,
        size, options, written=written,
    )  # fmt: skip


def _render_asset(project: ProjectMetadata, render: RenderRecord) -> Asset:
    return next(a for a in project.assets if a.id == render.id)


def audit_corrections(project: ProjectMetadata, draft: RenderRecord | None, notes: str = "") -> str:
    """Correcciones para la composición (B-046): las de la última auditoría con IA del boceto y
    las notas del usuario («auditoría manual»)."""
    parts = []
    if draft is not None and draft.audits:
        report = draft.audits[-1].report
        parts.append(f"Auditoría con IA ({report.verdict}, {report.score}/100): {report.summary}")
        if report.suggested_prompt_adjustments.strip():
            parts.append(f"Correcciones propuestas: {report.suggested_prompt_adjustments.strip()}")
    if notes.strip():
        parts.append(f"Notas del usuario: {notes.strip()}")
    return "\n".join(parts)


async def generate_composition(
    repo: ProjectRepository,
    client: FoundryClient,
    project_id: UUID,
    options: RenderOptions,
    draft_id: UUID | None = None,
    source: CompositionSource = "boceto",
    use_audit: bool = False,
    audit_notes: str = "",
) -> list[RenderRecord]:
    """Etapa 2 (B-045, B-055): composición a partir del boceto seleccionado o de la composición
    actual (la seleccionada), con las referencias activas como apoyo (hasta 12, por prioridad) y,
    si se pide, las correcciones de la auditoría del boceto.
    """
    project = await repo.get(project_id)
    options = RenderOptions(**{**options.__dict__, "quality": options.quality or "medium"})
    draft = (
        selected_render(project, draft_id, RenderStage.DRAFT)
        if draft_id
        else _selected(project, RenderStage.DRAFT)
    )
    if source == "composicion":
        start = _selected(project, RenderStage.COMPOSITION)
        if start is None:
            raise PipelineInputError("Selecciona una composición para generar a partir de ella")
        start_role = START_COMPOSITION_ROLE
    else:
        if draft is None:
            raise PipelineInputError("Selecciona un boceto para generar la composición")
        start, start_role = draft, START_DRAFT_ROLE
    supports, _ = split_supports(project, None)
    roles = [InputRole(_render_asset(project, start), start_role)]
    roles += [InputRole(a, SUPPORT_ROLE) for a in supports]
    size = resolve_size(Role.COMPOSITION_BUILDER, options.size or DEFAULT_GPT_SIZE, roles[0].asset)
    corrections = audit_corrections(project, draft, audit_notes) if use_audit else ""
    extras = {"Correcciones de la auditoría del boceto": corrections} if corrections else None
    prompt, written = await _prompt(
        repo, client, project, RenderStage.COMPOSITION, roles, size, options, extras
    )
    return await _run_stage(
        repo, client, project, RenderStage.COMPOSITION, [r.asset.id for r in roles], start,
        prompt, size, options, written=written,
    )  # fmt: skip


def _selected(project: ProjectMetadata, stage: RenderStage) -> RenderRecord | None:
    return next(
        (r for r in project.renders if r.stage is stage and r.status is RenderStatus.SELECTED),
        None,
    )


async def generate_final(
    repo: ProjectRepository,
    client: FoundryClient,
    project_id: UUID,
    options: RenderOptions,
    composition_id: UUID | None = None,
    source: FinalSource = "composicion",
    variant_of: UUID | None = None,
) -> list[RenderRecord]:
    """Etapa 3 (Paso 24: B-051, B-055, B-040): fotografía realista a partir de la composición
    seleccionada o del render final actual (el seleccionado), con las indicaciones globales del
    usuario. El renderizador solo recibe la imagen de partida y el prompt (sin referencias: lo
    marcado en las fichas llega como texto al PROMPT_ARCHITECT); 3:2 a 2448x1632 por defecto.

    `variant_of` («Otra versión»): repite tal cual el prompt, la imagen de partida y el tamaño de
    ese render final (la semilla del renderizador en Azure no es reproducible, Paso 18).
    """
    project = await repo.get(project_id)
    if variant_of is not None:
        return await _final_variant(repo, client, project, options, variant_of)
    options = RenderOptions(**{**options.__dict__, "seed": None, "quality": None})
    if source == "render_final":
        start = _selected(project, RenderStage.FINAL)
        if start is None:
            raise PipelineInputError("Selecciona un render final para generar a partir de él")
        start_role = FINAL_FROM_RENDER_ROLE
    else:
        start = (
            selected_render(project, composition_id, RenderStage.COMPOSITION)
            if composition_id
            else _selected(project, RenderStage.COMPOSITION)
        )
        if start is None:
            raise PipelineInputError("Selecciona una composición para el render final")
        start_role = FINAL_FROM_COMPOSITION_ROLE
    roles = [InputRole(_render_asset(project, start), start_role)]
    size = resolve_size(
        Role.REALISTIC_RENDERER, options.size or DEFAULT_RENDERER_SIZE, roles[0].asset
    )
    prompt, written = await _prompt(repo, client, project, RenderStage.FINAL, roles, size, options)
    return await _run_stage(
        repo, client, project, RenderStage.FINAL, [start.id], start, prompt, size, options,
        written=written,
    )  # fmt: skip


async def _final_variant(
    repo: ProjectRepository,
    client: FoundryClient,
    project: ProjectMetadata,
    options: RenderOptions,
    variant_of: UUID,
) -> list[RenderRecord]:
    original = next((r for r in project.renders if r.id == variant_of), None)
    if original is None:
        raise RenderNotFoundError(str(variant_of))
    if original.stage is not RenderStage.FINAL:
        raise PipelineInputError("Solo se hacen versiones de un render final")
    if original.prompt_info is None:  # imágenes de la v1: su prompt dependía de otras entradas
        raise PipelineInputError("Solo hay versiones de los renders finales con prompt automático")
    parent = next((r for r in project.renders if r.id == original.parent_render_id), None)
    written = WrittenPrompt(prompt=original.prompt_info, version=original.prompt_version or "")
    repeat = RenderOptions(n=options.n)  # sin indicaciones: el prompt va tal cual
    return await _run_stage(
        repo, client, project, RenderStage.FINAL, original.input_asset_ids[:1], parent,
        original.prompt, original.size, repeat, written=written, variant_of=original.id,
    )  # fmt: skip


async def select_render(repo: ProjectRepository, project_id: UUID, render_id: UUID) -> RenderRecord:
    """El usuario selecciona un render: uno solo por etapa (B-043)."""

    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, RenderRecord]:
        renders = list(metadata.renders)
        for i, render in enumerate(renders):
            if render.id == render_id:
                target = RenderStatus.SELECTED
                ensure_transition(RENDER_TRANSITIONS, render.status, target, "el render")
                now = utc_now()
                renders[i] = render.model_copy(update={"status": target, "decided_at": now})
                # El seleccionado anterior de la misma etapa vuelve a generado.
                for j, other in enumerate(renders):
                    if j != i and other.stage is render.stage and other.status is target:
                        ensure_transition(
                            RENDER_TRANSITIONS, other.status, RenderStatus.GENERATED, "el render"
                        )
                        renders[j] = other.model_copy(
                            update={"status": RenderStatus.GENERATED, "decided_at": now}
                        )
                return metadata.model_copy(update={"renders": renders}), renders[i]
        raise RenderNotFoundError(str(render_id))

    return await repo.mutate(project_id, change)


# --- Retoque de una zona (inpainting, Paso 13b) ---------------------------------------------


def inpaint_prompt(change: str, bounds: str, *, written: bool = False) -> str:
    """Prompt del retoque con máscara: el cambio debe quedar dentro de la zona pintada.

    `written`: el cambio ya es el prompt en inglés del PROMPT_ARCHITECT (Paso 23), que ya pide
    editar solo la zona; si no, es la instrucción del usuario en español.
    """
    keep = "same framing, geometry, perspective, camera, lighting, materials and colors"
    contain = (
        f"The area spans {bounds}. Everything you add or change must fit entirely inside "
        "that area, with a clear margin to its edges: nothing new may cross or touch them."
    )
    head = (
        change.strip()
        if written
        else "Edit only the transparent area of the mask. Requested change (in Spanish, apply "
        f"it): {change.strip()}"
    )
    return (
        f"{head}\n\n{contain}\n\nKeep everything else exactly as it is: {keep}. "
        "Blend the edit seamlessly with its surroundings."
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
    indications: str = "",
    use_audit: bool = False,
    audit_notes: str = "",
) -> RenderRecord:
    """Retoca la zona pintada de una composición con la máscara nativa del COMPOSITION_BUILDER.

    Paso 23: es «Generar con la composición actual» con «Usar el retoque»: el PROMPT_ARCHITECT
    escribe el prompt del cambio (con los límites de la zona, las referencias activas, las
    indicaciones y, si se pide, la auditoría del boceto) y el modelo recibe la composición y
    los apoyos. El resultado es la imagen completa que devuelve el modelo (B-038: sin
    recomponer), como imagen nueva de la misma etapa y sin seleccionar; la original no cambia.
    """
    if not instruction.strip():
        raise PipelineInputError("Describe el cambio que quieres en la zona pintada")
    project = await repo.get(project_id)
    source = next((r for r in project.renders if r.id == render_id), None)
    if source is None:
        raise RenderNotFoundError(str(render_id))
    if source.stage not in INPAINT_STAGES:
        raise PipelineInputError("Solo se pueden retocar composiciones")

    source_data = await repo.read_asset_bytes(project.id, source.id)
    width, height = _size_of(source_data)
    zone = await anyio.to_thread.run_sync(masks.edit_zone, mask_data, (width, height))
    covered = masks.check_coverage(zone)
    role, output_format = _STAGE_ROLES[source.stage]
    source_image = await prepare_image(source_data, INPUT_MAX_SIDE_PX)
    quality_used = quality or source.quality or "medium"
    size = f"{width}x{height}"
    if size not in GPT_IMAGE_SIZES:
        size = _DEFAULT_SIZES["gpt"][_orientation_of(width, height)]
    model_mask = await anyio.to_thread.run_sync(masks.model_mask, zone, _size_of(source_image.data))
    bounds = masks.zone_bounds_text(zone)

    supports, _ = split_supports(project, None)
    roles = [InputRole(_render_asset(project, source), RETOUCH_ROLE)]
    roles += [InputRole(a, SUPPORT_ROLE) for a in supports]
    retouch = (
        f"Cambio pedido por el usuario en la zona: {instruction.strip()}\n"
        f"Límites de la zona: {bounds}"
    )
    extras = {"Modo retoque": retouch}
    draft = _selected(project, RenderStage.DRAFT)
    corrections = audit_corrections(project, draft, audit_notes) if use_audit else ""
    if corrections:
        extras["Correcciones de la auditoría del boceto"] = corrections
    written = await write_prompt(
        repo, client, project, RenderStage.COMPOSITION, roles, active_references(project),
        indications, size, extras,
    )  # fmt: skip
    images = [source_image] + [
        await prepare_image(await repo.read_asset_bytes(project.id, a.id), INPUT_MAX_SIDE_PX)
        for a in supports
    ]
    request = ImageEditRequest(
        prompt=inpaint_prompt(written.prompt.prompt, bounds, written=True), size=size,
        quality=quality_used, output_format=output_format, images=images,
        mask=InputImage(data=model_mask, mime_type="image/png"),
    )  # fmt: skip

    result = await client.edit_image(role, request)
    content = await anyio.to_thread.run_sync(masks.fit_png, result.images[0].data, (width, height))
    total = _call_cost(client, role, result, images)
    record_id = uuid4()
    mask_file = f"{record_id}-mascara.png"
    record = RenderRecord(
        id=record_id,
        stage=source.stage,
        role=role,
        deployment=_deployment(client, role, result),
        prompt=request.prompt,
        prompt_info=written.prompt,
        prompt_version=written.version,
        input_asset_ids=[r.asset.id for r in roles],
        parent_render_id=source.parent_render_id,
        batch_id=uuid4(),
        size=f"{width}x{height}",
        quality=quality_used,
        request_id=current_request_id(),
        cost_eur=round(total, 6) if total is not None else None,
        inpaint=RenderInpaint(
            source_render_id=source.id,
            instruction=instruction.strip(),
            mask_file=mask_file,
            coverage=covered,
        ),
    )
    files = {mask_file: await anyio.to_thread.run_sync(masks.zone_png, zone)}
    await repo.add_render(project.id, record, content, "image/png", width, height, sidecars=files)
    return record
