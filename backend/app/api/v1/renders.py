"""Pipelines de imagen: boceto → composición → render final (con selección del usuario)."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import FoundryDep, RepositoryDep, SettingsDep
from app.api.uploads import inspect_upload, read_upload
from app.pipelines.auditor import audit_render
from app.pipelines.renders import (
    RenderNotFoundError,
    RenderOptions,
    decide_render,
    generate_composition,
    generate_drafts,
    generate_final,
    inpaint_render,
    reject_render,
    use_raw_output,
)
from app.telemetry import current_request_id, request_cost, telemetry_scope
from shared.models import AssetKind, RenderAudit, RenderRecord, RenderStage, RenderStatus

router = APIRouter(prefix="/projects/{project_id}/renders", tags=["renders"])


class _RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    brief_id: UUID | None = Field(default=None, description="Por defecto, el brief aprobado")
    size: str | None = Field(default=None, description="Por defecto, según la captura")
    prompt_override: str | None = Field(
        default=None, min_length=1, max_length=4_000, description="Sustituye el prompt del brief"
    )
    extra_instructions: str = Field(
        default="", max_length=2_000, description="Se añade al final del prompt"
    )


class DraftRequest(_RenderRequest):
    n: int = Field(default=2, ge=1, le=4)
    quality: Literal["low", "medium", "high", "auto"] = "low"


class CompositionRequest(_RenderRequest):
    draft_id: UUID | None = Field(default=None, description="Boceto seleccionado (opcional)")
    n: int = Field(default=1, ge=1, le=4)
    quality: Literal["low", "medium", "high", "auto"] = "medium"


class FinalRequest(_RenderRequest):
    composition_id: UUID = Field(description="Composición seleccionada")
    reference_ids: list[UUID] | None = Field(
        default=None, description="Referencias de textura/color (por defecto, las del brief)"
    )
    n: int = Field(default=1, ge=1, le=2)
    seed: int | None = None


class RenderRunResponse(BaseModel):
    renders: list[RenderRecord]
    cost_eur: float
    request_id: str | None


class AuditResponse(BaseModel):
    render: RenderRecord
    audit: RenderAudit
    cost_eur: float
    request_id: str | None


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    feedback: str = Field(min_length=1, max_length=2_000)
    regenerate: bool = Field(default=True, description="Generar una nueva imagen de la etapa")
    apply_audit_suggestions: bool = Field(
        default=True, description="Añadir al prompt las correcciones de la última auditoría"
    )


class RejectResponse(BaseModel):
    rejected: RenderRecord
    new_renders: list[RenderRecord]
    cost_eur: float
    request_id: str | None


def _options(body: _RenderRequest, **extra: object) -> RenderOptions:
    return RenderOptions(
        n=body.n,  # type: ignore[attr-defined]
        size=body.size,
        brief_id=body.brief_id,
        prompt_override=body.prompt_override,
        extra_instructions=body.extra_instructions,
        **extra,  # type: ignore[arg-type]
    )


async def _response(repo: RepositoryDep, project_id: UUID, renders: list) -> RenderRunResponse:
    return RenderRunResponse(
        renders=renders,
        cost_eur=await request_cost(repo, project_id),
        request_id=current_request_id(),
    )


@router.post("/drafts", status_code=status.HTTP_201_CREATED, response_model=RenderRunResponse)
async def create_drafts(
    project_id: UUID,
    repo: RepositoryDep,
    foundry: FoundryDep,
    body: Annotated[DraftRequest, Body()] = DraftRequest(),  # noqa: B008
) -> RenderRunResponse:
    """Etapa 1 (FAST_DRAFT): bocetos editando la captura de SketchUp con el brief aprobado."""
    with telemetry_scope(project_id):
        renders = await generate_drafts(
            repo, foundry, project_id, _options(body, quality=body.quality)
        )
    return await _response(repo, project_id, renders)


@router.post("/compositions", status_code=status.HTTP_201_CREATED, response_model=RenderRunResponse)
async def create_composition(
    project_id: UUID,
    repo: RepositoryDep,
    foundry: FoundryDep,
    body: Annotated[CompositionRequest, Body()] = CompositionRequest(),  # noqa: B008
) -> RenderRunResponse:
    """Etapa 2 (STRUCTURAL_COMPOSER): composición sobre la captura (+ boceto seleccionado)."""
    with telemetry_scope(project_id):
        renders = await generate_composition(
            repo, foundry, project_id, _options(body, quality=body.quality), body.draft_id
        )
    return await _response(repo, project_id, renders)


@router.post("/final", status_code=status.HTTP_201_CREATED, response_model=RenderRunResponse)
async def create_final(
    project_id: UUID, body: FinalRequest, repo: RepositoryDep, foundry: FoundryDep
) -> RenderRunResponse:
    """Etapa 3 (PHOTOREALISTIC_RENDERER): render con la composición seleccionada + referencias."""
    with telemetry_scope(project_id):
        renders = await generate_final(
            repo, foundry, project_id, _options(body, seed=body.seed),
            body.composition_id, body.reference_ids,
        )  # fmt: skip
    return await _response(repo, project_id, renders)


@router.get("", response_model=list[RenderRecord])
async def list_renders(
    project_id: UUID,
    repo: RepositoryDep,
    stage: Annotated[RenderStage | None, Query()] = None,
) -> list[RenderRecord]:
    """Historial de renders (más reciente primero). La imagen: `/assets/{id}/content`."""
    renders = (await repo.get(project_id)).renders
    return sorted(
        (r for r in renders if stage is None or r.stage is stage),
        key=lambda r: r.created_at,
        reverse=True,
    )


@router.post("/{render_id}/select", response_model=RenderRecord)
async def select_render(project_id: UUID, render_id: UUID, repo: RepositoryDep) -> RenderRecord:
    """El usuario elige este render: puede alimentar la etapa siguiente."""
    return await decide_render(repo, project_id, render_id, RenderStatus.SELECTED)


@router.post("/{render_id}/discard", response_model=RenderRecord)
async def discard_render(project_id: UUID, render_id: UUID, repo: RepositoryDep) -> RenderRecord:
    return await decide_render(repo, project_id, render_id, RenderStatus.DISCARDED)


@router.post("/{render_id}/audit", response_model=AuditResponse)
async def audit(
    project_id: UUID,
    render_id: UUID,
    repo: RepositoryDep,
    foundry: FoundryDep,
    settings: SettingsDep,
) -> AuditResponse:
    """GEOMETRIC_AUDITOR a demanda (rol más caro): compara con la captura y guarda el informe.

    No bloquea la selección: se puede seleccionar un render sin auditar.
    """
    with telemetry_scope(project_id):
        render, report = await audit_render(
            repo, foundry, project_id, render_id, settings.auditor.reasoning_effort
        )
    return AuditResponse(
        render=render,
        audit=report,
        cost_eur=await request_cost(repo, project_id),
        request_id=current_request_id(),
    )


@router.post("/{render_id}/reject", response_model=RejectResponse)
async def reject(
    project_id: UUID, render_id: UUID, body: RejectRequest, repo: RepositoryDep, foundry: FoundryDep
) -> RejectResponse:
    """Rechazo con comentarios; por defecto regenera la misma etapa con los comentarios (y las
    correcciones de la última auditoría) añadidos al prompt."""
    with telemetry_scope(project_id):
        rejected, new = await reject_render(
            repo, foundry, project_id, render_id, body.feedback, body.regenerate,
            body.apply_audit_suggestions,
        )  # fmt: skip
    return RejectResponse(
        rejected=rejected,
        new_renders=new,
        cost_eur=await request_cost(repo, project_id),
        request_id=current_request_id(),
    )


@router.post(
    "/{render_id}/inpaint", status_code=status.HTTP_201_CREATED, response_model=RenderRunResponse
)
async def inpaint(
    project_id: UUID,
    render_id: UUID,
    mask: Annotated[
        UploadFile,
        File(description="Imagen con la proporción del render; lo pintado es la zona a editar"),
    ],
    instruction: Annotated[str, Form(min_length=1, max_length=2_000)],
    repo: RepositoryDep,
    foundry: FoundryDep,
    settings: SettingsDep,
    quality: Annotated[Literal["low", "medium", "high", "auto"] | None, Form()] = None,
) -> RenderRunResponse:
    """Retoque de una zona de una composición o render final (multipart).

    Lo pintado en la máscara (opaco, o claro si no tiene transparencia) se regenera con la
    instrucción; el resto queda idéntico al original (recomposición local). Crea una imagen
    nueva de la misma etapa, sin seleccionar; la original no cambia.
    """
    content = await read_upload(mask, settings.storage.max_upload_bytes)
    await inspect_upload(content, AssetKind.RENDER)  # imagen real y sin daños
    with telemetry_scope(project_id):
        record = await inpaint_render(
            repo, foundry, project_id, render_id, content, instruction, quality=quality
        )
    return await _response(repo, project_id, [record])


InpaintFile = Literal["mascara", "bruto", "guia"]


@router.get("/{render_id}/inpaint/{file}", response_class=FileResponse)
async def inpaint_file(
    project_id: UUID, render_id: UUID, file: InpaintFile, repo: RepositoryDep
) -> FileResponse:
    """Archivos de un retoque: la máscara (blanco = zona), la salida **en bruto** del modelo
    (antes de recomponer) y la guía enviada al renderizador (solo en el render final)."""
    project = await repo.get(project_id)
    render = next((r for r in project.renders if r.id == render_id), None)
    if render is None:
        raise RenderNotFoundError(str(render_id))
    info = render.inpaint
    name = None
    if info is not None:
        name = {"mascara": info.mask_file, "bruto": info.raw_file, "guia": info.guide_file}[file]
    if name is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este render no tiene ese archivo")
    path = repo.render_file_path(project_id, name)
    media_type = "image/jpeg" if name.endswith(".jpeg") else "image/png"
    return FileResponse(path, media_type=media_type, filename=name)


@router.post("/{render_id}/raw", status_code=status.HTTP_201_CREATED, response_model=RenderRecord)
async def use_raw(project_id: UUID, render_id: UUID, repo: RepositoryDep) -> RenderRecord:
    """Usa la salida en bruto de un retoque (la imagen completa del modelo, sin recomponer) como
    imagen nueva de la etapa, sin seleccionar. Sin coste."""
    return await use_raw_output(repo, project_id, render_id)
