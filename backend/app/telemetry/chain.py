"""Coste acumulado de la cadena de un render: todas las llamadas que llevaron hasta él."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from pydantic import BaseModel

from app.telemetry.summary import CostTotals, GroupTotals, _accumulate, _group, _rounded
from shared.models import DesignBrief, ProjectMetadata, RenderRecord, TelemetryRecord
from shared.roles import Role

# Briefs (Paso 14) y fichas (Paso 16) anteriores sin `request_id`: su llamada se empareja
# por la hora.
LEGACY_WINDOW = timedelta(seconds=10)


class RenderChainCost(BaseModel):
    render_id: UUID
    renders: int  # imágenes de la cadena (incluidos intentos rechazados y retoques)
    briefs: int
    references: int = 0  # fichas de referencias que usó el brief
    totals: CostTotals  # llamadas reales (sin simulación)
    by_role: list[GroupTotals]
    simulated_calls: int = 0
    simulated_cost_eur: float = 0.0


def render_chain(project: ProjectMetadata, render_id: UUID) -> list[RenderRecord] | None:
    """El render y todo lo que lo precede: etapa anterior, imagen retocada, salida en bruto
    de la que procede, intentos rechazados que sustituye y renders usados como entrada."""
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
                current.previous_attempt_id,
                current.raw_of_render_id,
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


def _brief_request_ids(
    project: ProjectMetadata, brief_ids: set[UUID], records: list[TelemetryRecord]
) -> tuple[set[str], list[DesignBrief]]:
    by_id = {b.id: b for b in project.briefs}
    briefs, pending = {}, list(brief_ids)
    while pending:  # versiones rechazadas que llevaron al brief usado
        brief = by_id.get(pending.pop())
        if brief is None or brief.id in briefs:
            continue
        briefs[brief.id] = brief
        if brief.parent_id:
            pending.append(brief.parent_id)
    ids: set[str] = set()
    for brief in briefs.values():
        if brief.request_id:
            ids.add(brief.request_id)
        else:
            ids |= _legacy_ids(records, Role.PROMPT_ENGINEER, brief.created_at)
    return ids, list(briefs.values())


def _reference_request_ids(
    project: ProjectMetadata, briefs: list[DesignBrief], records: list[TelemetryRecord]
) -> tuple[set[str], int]:
    """Peticiones que indexaron las fichas usadas por los briefs (B-022). Si una petición indexó
    a la vez otras referencias, cuentan también (fracciones de céntimo)."""
    wanted = {i for brief in briefs for i in brief.reference_asset_ids}
    analyses = [a.analysis for a in project.assets if a.id in wanted and a.analysis]
    ids: set[str] = set()
    for analysis in analyses:
        if analysis.request_id:
            ids.add(analysis.request_id)
        else:
            ids |= _legacy_ids(records, Role.REFERENCE_ANALYST, analysis.analyzed_at)
    return ids, len(analyses)


def chain_cost(
    project: ProjectMetadata, records: list[TelemetryRecord], render_id: UUID
) -> RenderChainCost | None:
    """Suma las llamadas de la cadena por `request_id`: lotes completos (todas las variantes
    generadas a la vez), auditorías, retoques, regeneraciones y el brief (con sus versiones)."""
    chain = render_chain(project, render_id)
    if chain is None:
        return None
    request_ids = {r.request_id for r in chain} | {a.request_id for r in chain for a in r.audits}
    brief_ids, briefs = _brief_request_ids(project, {r.brief_id for r in chain}, records)
    reference_ids, references = _reference_request_ids(project, briefs, records)
    request_ids = (request_ids | brief_ids | reference_ids) - {None}
    calls = [r for r in records if r.request_id in request_ids]
    real = [r for r in calls if not r.simulated]
    simulated = [r for r in calls if r.simulated]
    totals = CostTotals()
    for record in real:
        _accumulate(totals, record)
    return RenderChainCost(
        render_id=render_id,
        renders=len(chain),
        briefs=len(briefs),
        references=references,
        totals=_rounded(totals),
        by_role=_group(real, lambda r: r.role.value),  # type: ignore[arg-type]
        simulated_calls=len(simulated),
        simulated_cost_eur=round(sum(r.cost_eur or 0 for r in simulated), 6),
    )
