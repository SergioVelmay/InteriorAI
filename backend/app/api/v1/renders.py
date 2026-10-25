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
    generate_composition,
    generate_drafts,
    generate_final,
    inpaint_render,
    select_render,
)
from app.telemetry import current_request_id, request_cost, telemetry_scope
from shared.models import AssetKind, RenderAudit, RenderRecord, RenderStage

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
    """Bocetos (B-036, B-040, B-043): de 1 a 8 variantes (4 por defecto), calidad media y
    formato 1536x1024 (3:2) por defecto. El prompt lo escribe el PROMPT_ENGINEER."""

    n: int = Field(default=4, ge=1, le=8)
    quality: Literal["low", "medium", "high", "auto"] = "medium"


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
    """Etapa 1 (FAST_DRAFT): bocetos a partir de las referencias activas, con prompt automático."""
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
async def select(project_id: UUID, render_id: UUID, repo: RepositoryDep) -> RenderRecord:
    """El usuario elige este render: puede alimentar la etapa siguiente."""
    return await select_render(repo, project_id, render_id)


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
    """Retoque de una zona de una composición (multipart).

    Lo pintado en la máscara (opaco, o claro si no tiene transparencia) se edita con la
    instrucción mediante la máscara nativa del modelo, que devuelve la imagen completa (B-038).
    Crea una imagen nueva de la misma etapa, sin seleccionar; la original no cambia.
    """
    content = await read_upload(mask, settings.storage.max_upload_bytes)
    await inspect_upload(content, AssetKind.RENDER)  # imagen real y sin daños
    with telemetry_scope(project_id):
        record = await inpaint_render(
            repo, foundry, project_id, render_id, content, instruction, quality=quality
        )
    return await _response(repo, project_id, [record])


InpaintFile = Literal["mascara"]


@router.get("/{render_id}/inpaint/{file}", response_class=FileResponse)
async def inpaint_file(
    project_id: UUID, render_id: UUID, file: InpaintFile, repo: RepositoryDep
) -> FileResponse:
    """Máscara de un retoque (blanco = zona editada)."""
    project = await repo.get(project_id)
    render = next((r for r in project.renders if r.id == render_id), None)
    if render is None:
        raise RenderNotFoundError(str(render_id))
    info = render.inpaint
    name = info.mask_file if info is not None else None
    if name is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este render no tiene ese archivo")
    path = repo.render_file_path(project_id, name)
    media_type = "image/jpeg" if name.endswith(".jpeg") else "image/png"
    return FileResponse(path, media_type=media_type, filename=name)
