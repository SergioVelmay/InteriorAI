"""Pipelines de texto: indexación de referencias (REFERENCE_ANALYST) y briefs (PROMPT_ENGINEER).

Los briefs siguen el ciclo HITL: propuesto → (editado) → aprobado | rechazado (→ nueva versión).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import FoundryDep, RepositoryDep
from app.hitl.briefs import (
    BriefContentUpdate,
    approve_brief,
    edit_brief,
    find_brief,
    reject_brief,
)
from app.pipelines.prompt_engineer import create_brief
from app.pipelines.reference_analyst import index_references, validate_analysis
from app.telemetry import current_request_id, request_cost, telemetry_scope
from shared.models import Asset, DesignBrief, ReferenceAnalysis

router = APIRouter(prefix="/projects/{project_id}", tags=["pipelines"])


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IndexRequest(_Body):
    asset_ids: list[UUID] | None = Field(
        default=None, description="Referencias a indexar (por defecto, todas las pendientes)"
    )
    force: bool = Field(default=False, description="Reindexar también las ya analizadas")


class IndexFailure(BaseModel):
    asset_id: UUID
    error: str


class RunCost(BaseModel):
    cost_eur: float = Field(description="Coste estimado de las llamadas a IA de esta petición")
    request_id: str | None


class IndexResponse(RunCost):
    indexed: list[Asset]
    skipped: list[UUID]
    failed: list[IndexFailure]


class BriefCreate(_Body):
    instructions: str = Field(default="", max_length=4_000)


class BriefRunResponse(RunCost):
    brief: DesignBrief


class BriefReject(_Body):
    feedback: str = Field(min_length=1, max_length=4_000)
    regenerate: bool = Field(default=True, description="Generar a continuación una nueva versión")


class BriefRejectResponse(RunCost):
    rejected: DesignBrief
    new_brief: DesignBrief | None


async def _cost(repo: RepositoryDep, project_id: UUID) -> dict:
    return {"cost_eur": await request_cost(repo, project_id), "request_id": current_request_id()}


# --- Referencias ------------------------------------------------------------------------


@router.post("/references/index", response_model=IndexResponse)
async def index_project_references(
    project_id: UUID,
    repo: RepositoryDep,
    foundry: FoundryDep,
    body: Annotated[IndexRequest, Body()] = IndexRequest(),  # noqa: B008
) -> IndexResponse:
    """Analiza las referencias con el REFERENCE_ANALYST y guarda su ficha (estado `proposed`)."""
    with telemetry_scope(project_id):
        result = await index_references(repo, foundry, project_id, body.asset_ids, body.force)
    return IndexResponse(
        indexed=result.indexed,
        skipped=result.skipped,
        failed=[IndexFailure(asset_id=a, error=e) for a, e in result.failed],
        **await _cost(repo, project_id),
    )


@router.put("/assets/{asset_id}/analysis", response_model=Asset)
async def update_reference_analysis(
    project_id: UUID, asset_id: UUID, analysis: ReferenceAnalysis, repo: RepositoryDep
) -> Asset:
    """El usuario revisa o corrige la ficha: queda `validated`."""
    return await validate_analysis(repo, project_id, asset_id, analysis)


# --- Briefs -------------------------------------------------------------------------------


@router.post("/briefs", status_code=status.HTTP_201_CREATED, response_model=BriefRunResponse)
async def generate_brief(
    project_id: UUID,
    repo: RepositoryDep,
    foundry: FoundryDep,
    body: Annotated[BriefCreate, Body()] = BriefCreate(),  # noqa: B008
) -> BriefRunResponse:
    """Genera una nueva versión del brief (estado `propuesto`) con el PROMPT_ENGINEER."""
    with telemetry_scope(project_id):
        brief = await create_brief(repo, foundry, project_id, body.instructions)
    return BriefRunResponse(brief=brief, **await _cost(repo, project_id))


@router.get("/briefs", response_model=list[DesignBrief])
async def list_briefs(project_id: UUID, repo: RepositoryDep) -> list[DesignBrief]:
    return sorted((await repo.get(project_id)).briefs, key=lambda b: b.version, reverse=True)


@router.get("/briefs/{brief_id}", response_model=DesignBrief)
async def get_brief(project_id: UUID, brief_id: UUID, repo: RepositoryDep) -> DesignBrief:
    return find_brief(await repo.get(project_id), brief_id)


@router.patch("/briefs/{brief_id}", response_model=DesignBrief)
async def update_brief(
    project_id: UUID, brief_id: UUID, update: BriefContentUpdate, repo: RepositoryDep
) -> DesignBrief:
    """Edita un brief `propuesto` (incluidos los prompts de imagen). 409 en otro estado."""
    return await edit_brief(repo, project_id, brief_id, update)


@router.post("/briefs/{brief_id}/approve", response_model=DesignBrief)
async def approve(project_id: UUID, brief_id: UUID, repo: RepositoryDep) -> DesignBrief:
    """Aprueba el brief: solo un brief aprobado puede alimentar la generación de imágenes."""
    return await approve_brief(repo, project_id, brief_id)


@router.post("/briefs/{brief_id}/reject", response_model=BriefRejectResponse)
async def reject(
    project_id: UUID,
    brief_id: UUID,
    body: BriefReject,
    repo: RepositoryDep,
    foundry: FoundryDep,
) -> BriefRejectResponse:
    """Rechaza el brief con comentarios y, por defecto, genera la siguiente versión."""
    rejected = await reject_brief(repo, project_id, brief_id, body.feedback)
    new_brief = None
    if body.regenerate:
        with telemetry_scope(project_id):
            new_brief = await create_brief(
                repo, foundry, project_id, rejected.instructions, parent=rejected
            )
    return BriefRejectResponse(
        rejected=rejected, new_brief=new_brief, **await _cost(repo, project_id)
    )
