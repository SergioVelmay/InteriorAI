"""Agregados de telemetría para el dashboard de costes: totales y desgloses por rol, día,
despliegue y proyecto, de un proyecto o de todos, con o sin las llamadas simuladas."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from uuid import UUID

from pydantic import BaseModel

from shared.models import TelemetryRecord


class CostTotals(BaseModel):
    calls: int = 0
    errors: int = 0
    unpriced_calls: int = 0
    cost_eur: float = 0.0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    images_out: int = 0
    megapixels_out: float = 0.0
    latency_s: float = 0.0


class GroupTotals(CostTotals):
    key: str
    label: str | None = None  # nombre legible (p. ej. del proyecto)


class CostRecord(TelemetryRecord):
    """Registro de telemetría con el proyecto al que pertenece."""

    project_id: UUID | None = None
    project_name: str | None = None


class CostSummary(BaseModel):
    project_id: UUID | None  # None = todos los proyectos
    currency: str
    estimated: bool = True  # precios de lista; la cifra real está en Azure Cost Management
    includes_simulated: bool  # hay llamadas simuladas en los totales
    simulated_excluded: int = 0  # llamadas simuladas que se han dejado fuera
    totals: CostTotals
    by_role: list[GroupTotals]
    by_day: list[GroupTotals]
    by_deployment: list[GroupTotals]
    by_project: list[GroupTotals] = []
    records: list[CostRecord]


def _accumulate(totals: CostTotals, record: TelemetryRecord) -> None:
    totals.calls += 1
    totals.errors += record.status == "error"
    if record.cost_eur is None:
        totals.unpriced_calls += 1
    else:
        totals.cost_eur += record.cost_eur
    totals.input_tokens += record.input_tokens
    totals.cached_input_tokens += record.cached_input_tokens
    totals.output_tokens += record.output_tokens
    totals.reasoning_tokens += record.reasoning_tokens
    totals.images_out += record.images_out
    totals.megapixels_out += record.megapixels_out
    totals.latency_s += record.latency_s


def _rounded(totals: CostTotals) -> CostTotals:
    totals.cost_eur = round(totals.cost_eur, 6)
    totals.megapixels_out = round(totals.megapixels_out, 4)
    totals.latency_s = round(totals.latency_s, 3)
    return totals


def _group(
    records: Iterable[CostRecord],
    key: Callable[[CostRecord], str],
    label: Callable[[CostRecord], str | None] = lambda r: None,
) -> list[GroupTotals]:
    groups: dict[str, GroupTotals] = {}
    for record in records:
        k = key(record)
        _accumulate(groups.setdefault(k, GroupTotals(key=k, label=label(record))), record)
    return sorted((_rounded(g) for g in groups.values()), key=lambda g: g.key)  # type: ignore[misc]


def summarize(
    project_id: UUID | None,
    records: list[CostRecord],
    currency: str,
    limit: int,
    include_simulated: bool = True,
) -> CostSummary:
    kept = [r for r in records if include_simulated or not r.simulated]
    totals = CostTotals()
    for record in kept:
        _accumulate(totals, record)
    latest = sorted(kept, key=lambda r: r.timestamp, reverse=True)[:limit]
    return CostSummary(
        project_id=project_id,
        currency=currency,
        includes_simulated=any(r.simulated for r in kept),
        simulated_excluded=len(records) - len(kept),
        totals=_rounded(totals),
        by_role=_group(kept, lambda r: r.role.value),
        by_day=_group(kept, lambda r: r.timestamp.date().isoformat()),
        by_deployment=_group(kept, lambda r: r.deployment),
        by_project=_group(kept, lambda r: str(r.project_id), lambda r: r.project_name),
        records=latest,
    )


def with_project(
    records: Iterable[TelemetryRecord], project_id: UUID, project_name: str
) -> list[CostRecord]:
    return [
        CostRecord(**r.model_dump(), project_id=project_id, project_name=project_name)
        for r in records
    ]
