"""Costes y telemetría de las llamadas a la IA."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.deps import RepositoryDep
from app.telemetry.pricing import PricingTable
from app.telemetry.summary import CostSummary, summarize

router = APIRouter(tags=["costes"])


def _pricing(request: Request) -> PricingTable | None:
    return request.app.state.foundry.pricing


@router.get("/projects/{project_id}/costs", response_model=CostSummary)
async def project_costs(
    project_id: UUID,
    repo: RepositoryDep,
    request: Request,
    limit: Annotated[int, Query(ge=0, le=1000, description="Últimos registros a devolver")] = 50,
) -> CostSummary:
    """Totales y desgloses por rol, día y despliegue. Coste **estimado** con precios de lista."""
    log = await repo.read_telemetry(project_id)
    pricing = _pricing(request)
    currency = pricing.currency if pricing else "EUR"
    return summarize(project_id, log.records, currency, limit)


@router.get("/pricing", response_model=PricingTable)
async def pricing_table(request: Request) -> PricingTable:
    pricing = _pricing(request)
    if pricing is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Tabla de precios no disponible (revisa PRICING_FILE)"
        )
    return pricing
