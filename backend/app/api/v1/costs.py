"""Costes y telemetría de las llamadas a la IA."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.deps import RepositoryDep, SettingsDep
from app.pipelines.renders import RenderNotFoundError
from app.telemetry.chain import RenderChainCost, chain_cost
from app.telemetry.pricing import PricingTable
from app.telemetry.summary import (
    CostAlerts,
    CostRecord,
    CostSummary,
    cost_alerts,
    current_deployments,
    current_roles,
    summarize,
    with_project,
)

router = APIRouter(tags=["costes"])

Limit = Annotated[int, Query(ge=0, le=1000, description="Últimos registros a devolver")]
IncludeSimulated = Annotated[bool, Query(description="Incluir las llamadas simuladas (modo mock)")]


def _pricing(request: Request) -> PricingTable | None:
    return request.app.state.foundry.pricing


def _currency(request: Request) -> str:
    pricing = _pricing(request)
    return pricing.currency if pricing else "EUR"


@router.get("/projects/{project_id}/costs", response_model=CostSummary)
async def project_costs(
    project_id: UUID,
    repo: RepositoryDep,
    request: Request,
    settings: SettingsDep,
    limit: Limit = 50,
    include_simulated: IncludeSimulated = True,
) -> CostSummary:
    """Totales y desgloses por rol, día y despliegue. Coste **estimado** con precios de lista.
    Cada llamada cuenta en el rol que hoy tiene su despliegue (el original, en `call_role`)."""
    project = await repo.get(project_id)
    log = await repo.read_telemetry(project_id)
    records = with_project(log.records, project.id, project.name)
    return summarize(
        project_id, records, _currency(request), limit, include_simulated, project.name,
        current_roles(settings), current_deployments(settings),
    )  # fmt: skip


@router.get("/costs", response_model=CostSummary)
async def all_costs(
    repo: RepositoryDep,
    request: Request,
    settings: SettingsDep,
    limit: Limit = 50,
    include_simulated: IncludeSimulated = True,
) -> CostSummary:
    """Lo mismo para todos los proyectos (con desglose por proyecto). Los proyectos en la
    papelera no cuentan."""
    records: list[CostRecord] = []
    for project in await repo.list_projects():
        log = await repo.read_telemetry(project.id)
        records += with_project(log.records, project.id, project.name)
    return summarize(
        None, records, _currency(request), limit, include_simulated,
        deployment_roles=current_roles(settings),
        role_deployments=current_deployments(settings),
    )  # fmt: skip


@router.get("/costs/alerts", response_model=CostAlerts)
async def alerts(repo: RepositoryDep, request: Request, settings: SettingsDep) -> CostAlerts:
    """Gasto real (sin simulación) por proyecto y total frente a los umbrales de aviso
    (`COST_ALERT_PROJECT_EUR`, `COST_ALERT_TOTAL_EUR`). Solo informa."""
    records: list[CostRecord] = []
    names = {}
    for project in await repo.list_projects():
        names[project.id] = project.name
        log = await repo.read_telemetry(project.id)
        records += with_project(log.records, project.id, project.name)
    limits = settings.cost_alerts
    return cost_alerts(records, names, _currency(request), limits.project_eur, limits.total_eur)


@router.get("/projects/{project_id}/renders/{render_id}/cost", response_model=RenderChainCost)
async def render_cost(
    project_id: UUID, render_id: UUID, repo: RepositoryDep, settings: SettingsDep
) -> RenderChainCost:
    """Coste acumulado para llegar a esta imagen: brief (y sus versiones), lotes de cada etapa,
    intentos rechazados, retoques y auditorías de la cadena. Sin las llamadas simuladas en el
    total (van aparte)."""
    project = await repo.get(project_id)
    log = await repo.read_telemetry(project_id)
    result = chain_cost(project, log.records, render_id, current_roles(settings))
    if result is None:
        raise RenderNotFoundError(str(render_id))
    return result


@router.get("/pricing", response_model=PricingTable)
async def pricing_table(request: Request) -> PricingTable:
    pricing = _pricing(request)
    if pricing is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Tabla de precios no disponible (revisa PRICING_FILE)"
        )
    return pricing
