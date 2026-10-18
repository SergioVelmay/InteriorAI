"""Observabilidad y control de costes de las llamadas a la IA."""

from __future__ import annotations

import logging
from uuid import UUID

from app.foundry import create_foundry_client
from app.telemetry.context import current_request_id, request_scope, telemetry_scope
from app.telemetry.metered import MeteredFoundryClient, TelemetryReader, TelemetrySink
from app.telemetry.pricing import PricingTable, estimate_cost, load_pricing, missing_prices
from shared import Settings
from shared.roles import Role

logger = logging.getLogger("interiorai.telemetry")


async def request_cost(sink: TelemetryReader, project_id: UUID) -> float:
    """Coste estimado de las llamadas a IA hechas en la petición HTTP actual."""
    request_id = current_request_id()
    if request_id is None:
        return 0.0
    log = await sink.read_telemetry(project_id)
    return round(sum(r.cost_eur or 0 for r in log.records if r.request_id == request_id), 6)


def create_metered_client(
    settings: Settings, sink: TelemetrySink, pricing: PricingTable | None
) -> MeteredFoundryClient:
    """Cliente de IA (mock o Azure) con telemetría y coste por llamada.

    Se registra el despliegue configurado del rol incluso en mock, para estimar con precios reales.
    """
    if pricing is not None:
        configured = [settings.deployment_for(role) for role in Role]
        if missing := missing_prices(pricing, configured):
            logger.warning("Despliegues sin precio en pricing.yaml: %s", ", ".join(missing))
    return MeteredFoundryClient(
        inner=create_foundry_client(settings),
        pricing=pricing,
        sink=sink,
        deployment_for=settings.deployment_for,
        simulated=settings.is_mock,
    )


__all__ = [
    "MeteredFoundryClient",
    "PricingTable",
    "create_metered_client",
    "current_request_id",
    "estimate_cost",
    "load_pricing",
    "request_cost",
    "request_scope",
    "telemetry_scope",
]
