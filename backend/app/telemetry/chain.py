"""Coste acumulado de la cadena de un render: todas las llamadas que llevaron hasta él."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from pydantic import BaseModel

from app.telemetry.summary import CostTotals, GroupTotals, _accumulate, _group, _rounded
from shared.models import ProjectMetadata, RenderRecord, TelemetryRecord
from shared.roles import Role

# Fichas anteriores al Paso 16, sin `request_id`: su llamada se empareja por la hora.
LEGACY_WINDOW = timedelta(seconds=10)


class RenderChainCost(BaseModel):
    render_id: UUID
    renders: int  # imágenes de la cadena (incluidos los retoques)
    references: int = 0  # recetas de las referencias que se enviaron como imagen en la cadena
    totals: CostTotals  # llamadas reales (sin simulación)
    by_role: list[GroupTotals]
    simulated_calls: int = 0
    simulated_cost_eur: float = 0.0


def render_chain(project: ProjectMetadata, render_id: UUID) -> list[RenderRecord] | None:
    """El render y todo lo que lo precede: etapa anterior, imagen retocada y renders usados
    como entrada."""
    by_id = {r.id: r for r in project.renders}
    if render_id not in by_id:
        return None
    chain: dict[UUID, RenderRecord] = {}
    pending = [render_id]
    while pending:
        current = by_id.get(pending.pop())
        if current is None or current.id in chain:
            continue
        chain[current.id] = current
        pending += [
            i
            for i in (
                current.parent_render_id,
                current.inpaint.source_render_id if current.inpaint else None,
                *current.input_asset_ids,
            )
            if i is not None
        ]
    return list(chain.values())


def _legacy_ids(records: list[TelemetryRecord], role: Role, when: datetime) -> set[str]:
    return {
        r.request_id
        for r in records
        if r.role is role and r.request_id and abs(r.timestamp - when) <= LEGACY_WINDOW
    }


def _reference_request_ids(
    project: ProjectMetadata, chain: list[RenderRecord], records: list[TelemetryRecord]
) -> tuple[set[str], int]:
    """Peticiones que analizaron las referencias enviadas como imagen en la cadena (B-022, Paso
    33). Si una petición analizó a la vez otras referencias, cuentan también (céntimos)."""
    wanted = {i for render in chain for i in render.input_asset_ids}
    sheets = [a.sheet for a in project.assets if a.id in wanted and a.sheet is not None]
    ids: set[str] = set()
    for sheet in sheets:
        if sheet.request_id:
            ids.add(sheet.request_id)
        else:
            ids |= _legacy_ids(records, Role.REFERENCE_ANALYST, sheet.analyzed_at)
    return ids, len(sheets)


def chain_cost(
    project: ProjectMetadata,
    records: list[TelemetryRecord],
    render_id: UUID,
    deployment_roles: dict[str, Role] | None = None,
) -> RenderChainCost | None:
    """Suma las llamadas de la cadena por `request_id`: lotes completos (todas las variantes
    generadas a la vez, con su prompt automático), auditorías, retoques y las recetas de las
    referencias usadas."""
    chain = render_chain(project, render_id)
    if chain is None:
        return None
    request_ids = {r.request_id for r in chain} | {a.request_id for r in chain for a in r.audits}
    reference_ids, references = _reference_request_ids(project, chain, records)
    request_ids = (request_ids | reference_ids) - {None}
    calls = [r for r in records if r.request_id in request_ids]
    real = [r for r in calls if not r.simulated]
    simulated = [r for r in calls if r.simulated]
    totals = CostTotals()
    for record in real:
        _accumulate(totals, record)
    return RenderChainCost(
        render_id=render_id,
        renders=len(chain),
        references=references,
        totals=_rounded(totals),
        # Rol actual de cada despliegue, como en Costes IA (Paso 26)
        by_role=_group(
            real,  # type: ignore[arg-type]
            lambda r: (deployment_roles or {}).get(r.deployment, r.role).value,
        ),
        simulated_calls=len(simulated),
        simulated_cost_eur=round(sum(r.cost_eur or 0 for r in simulated), 6),
    )
