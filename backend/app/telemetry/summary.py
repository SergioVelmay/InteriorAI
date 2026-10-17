"""Agregados de telemetría para el dashboard de costes (totales, por rol, día y despliegue)."""

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


class CostSummary(BaseModel):
    project_id: UUID
    currency: str
    estimated: bool = True  # precios de lista; la cifra real está en Azure Cost Management
    includes_simulated: bool
    totals: CostTotals
    by_role: list[GroupTotals]
    by_day: list[GroupTotals]
    by_deployment: list[GroupTotals]
    records: list[TelemetryRecord]


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
    records: Iterable[TelemetryRecord], key: Callable[[TelemetryRecord], str]
) -> list[GroupTotals]:
    groups: dict[str, GroupTotals] = {}
    for record in records:
        k = key(record)
        _accumulate(groups.setdefault(k, GroupTotals(key=k)), record)
    return sorted((_rounded(g) for g in groups.values()), key=lambda g: g.key)  # type: ignore[misc]


def summarize(
    project_id: UUID, records: list[TelemetryRecord], currency: str, limit: int
) -> CostSummary:
    totals = CostTotals()
    for record in records:
        _accumulate(totals, record)
    latest = sorted(records, key=lambda r: r.timestamp, reverse=True)[:limit]
    return CostSummary(
        project_id=project_id,
        currency=currency,
        includes_simulated=any(r.simulated for r in records),
        totals=_rounded(totals),
        by_role=_group(records, lambda r: r.role.value),
        by_day=_group(records, lambda r: r.timestamp.date().isoformat()),
        by_deployment=_group(records, lambda r: r.deployment),
        records=latest,
    )
