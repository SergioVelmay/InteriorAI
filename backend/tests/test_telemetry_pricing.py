from pathlib import Path

import pytest

from app.foundry.types import Usage
from app.telemetry.pricing import PricingTable, estimate_cost, load_pricing, missing_prices

PRICING_FILE = Path(__file__).resolve().parents[2] / "config" / "pricing.yaml"
DEPLOYMENTS = [
    "gpt-6.1-sol",
    "gpt-6-astra",
    "gpt-6-luna",
    "gpt-image-2.5-flare",
    "gpt-image-2.5-sunburst",
    "FLUX.2-pro",
]


@pytest.fixture(scope="module")
def table() -> PricingTable:
    loaded = load_pricing(PRICING_FILE)
    assert loaded is not None
    return loaded


def with_overrides(table: PricingTable, **changes: object) -> PricingTable:
    return table.model_copy(update=changes)


@pytest.fixture(scope="module")
def list_prices(table: PricingTable) -> PricingTable:
    """Precios de lista tal cual y megapíxel decimal: para comprobar las fórmulas."""
    return with_overrides(table, billing_factor=1.0, megapixel_px=1_000_000)


def test_repo_pricing_file_is_valid_and_complete(table: PricingTable) -> None:
    assert table.currency == "EUR"
    assert table.deployment_type == "global"
    assert table.long_context_threshold_tokens == 272_000
    assert table.megapixel_rounding == "exact"
    assert table.megapixel_px == 1_048_576 and table.billing_factor == 1.0  # sin factor
    assert table.deployments["FLUX.2-pro"].reference_mode == "pixels"
    assert missing_prices(table, DEPLOYMENTS) == []
    assert missing_prices(table, [*DEPLOYMENTS, "otro"]) == ["otro"]


def test_real_auditor_call_from_step_6(list_prices: PricingTable) -> None:
    """Llamada real del Paso 6: 74 de entrada y 1.084 de salida (1.012 de razonamiento)."""
    usage = Usage(input_tokens=74, output_tokens=1084, reasoning_tokens=1012)
    cost = estimate_cost(list_prices, "gpt-6-astra", usage)
    assert cost is not None
    assert cost.tier == "global/short"
    assert cost.parts["input"] == pytest.approx(74 * 8.80 / 1e6)
    assert cost.parts["output"] == pytest.approx(1084 * 44.00 / 1e6)
    assert cost.total == pytest.approx(0.0483472)


def test_cached_and_cache_write_tokens(list_prices: PricingTable) -> None:
    usage = Usage(
        input_tokens=10_000, cached_input_tokens=6_000, cache_write_tokens=1_000, output_tokens=0
    )
    cost = estimate_cost(list_prices, "gpt-6.1-sol", usage)
    assert cost is not None
    assert cost.parts["input"] == pytest.approx(3_000 * 1.76 / 1e6)
    assert cost.parts["cached_input"] == pytest.approx(6_000 * 0.09 / 1e6)
    assert cost.parts["cache_write"] == pytest.approx(1_000 * 2.20 / 1e6)


def test_long_context_above_threshold(list_prices: PricingTable) -> None:
    short = estimate_cost(list_prices, "gpt-6-luna", Usage(input_tokens=272_000))
    long = estimate_cost(list_prices, "gpt-6-luna", Usage(input_tokens=272_001))
    assert short is not None and long is not None
    assert short.tier == "global/short"
    assert long.tier == "global/long"
    assert long.total == pytest.approx(272_001 * 0.176 / 1e6)


def test_data_zone_rates(list_prices: PricingTable) -> None:
    cost = estimate_cost(
        with_overrides(list_prices, deployment_type="data_zone"),
        "gpt-6-astra",
        Usage(input_tokens=100_000),  # por debajo del umbral de contexto largo
    )
    assert cost is not None
    assert cost.tier == "data_zone/short"
    assert cost.total == pytest.approx(100_000 * 10.56 / 1e6)


def test_image_tokens_split_text_and_image(list_prices: PricingTable) -> None:
    usage = Usage(
        input_tokens=1053, input_text_tokens=21, input_image_tokens=1032, output_tokens=196
    )
    cost = estimate_cost(list_prices, "gpt-image-2.5-sunburst", usage)
    assert cost is not None
    assert cost.parts["input_text"] == pytest.approx(21 * 4.40 / 1e6)
    assert cost.parts["input_image"] == pytest.approx(1032 * 7.04 / 1e6)
    assert cost.parts["output"] == pytest.approx(196 * 26.40 / 1e6)


def test_image_tokens_without_breakdown_count_as_text(list_prices: PricingTable) -> None:
    cost = estimate_cost(
        list_prices, "gpt-image-2.5-flare", Usage(input_tokens=24, output_tokens=196)
    )
    assert cost is not None
    assert cost.parts["input_text"] == pytest.approx(24 * 4.40 / 1e6)
    assert cost.total == pytest.approx((24 * 4.40 + 196 * 26.40) / 1e6)


def test_flux_megapixels_exact(list_prices: PricingTable) -> None:
    cost = estimate_cost(list_prices, "FLUX.2-pro", Usage(), images_out=[(1024, 1024)])
    assert cost is not None
    assert cost.tier == "megapixels/exact"
    assert cost.total == pytest.approx(0.0264 + 0.048576 * 0.0132)  # 0,02704 €


def test_flux_megapixels_ceil_and_references(list_prices: PricingTable) -> None:
    ceil = with_overrides(list_prices, megapixel_rounding="ceil")
    cost = estimate_cost(
        ceil, "FLUX.2-pro", Usage(), images_out=[(1024, 1024)], references=[(1000, 1000)] * 2
    )
    assert cost is not None
    assert cost.parts["initial_mp"] == pytest.approx(0.0264)
    assert cost.parts["additional_mp"] == pytest.approx(0.0132)  # 1,05 MP → 2 MP
    assert cost.parts["reference_mp"] == pytest.approx(2 * 0.0132)


INVOICE_FACTOR = 0.98463  # factura ≈ lista por 0,98463 en todos los medidores (10/2026)


def test_repo_pricing_stays_just_above_the_invoices(table: PricingTable) -> None:
    """Facturas reales (B-011, Paso 39): con los precios de lista, sin factor, la estimación
    queda un 1,5 % por encima de lo facturado; nunca por debajo."""
    astra = estimate_cost(  # auditoría del 18/10/2026: 0,290049 € facturados
        table, "gpt-6-astra", Usage(input_tokens=11_861, cache_write_tokens=11_855,
                                    output_tokens=3_730),
    )  # fmt: skip
    assert astra is not None and astra.total * INVOICE_FACTOR == pytest.approx(0.290049, abs=2e-5)
    flare = estimate_cost(  # bocetos del 18/10/2026: 0,109456 € facturados
        table, "gpt-image-2.5-flare",
        Usage(input_text_tokens=666, input_image_tokens=9_048, output_tokens=1_687),
    )  # fmt: skip
    assert flare is not None and flare.total * INVOICE_FACTOR == pytest.approx(0.109456, abs=2e-5)
    # FLUX del 26/10/2026: dos renders de 2448x1632 desde composiciones de 1536x1024,
    # 0,164022 € facturados (cada referencia, por su tamaño en MP binario)
    flux = estimate_cost(
        table, "FLUX.2-pro", Usage(), images_out=[(2448, 1632)], references=[(1536, 1024)]
    )
    assert flux is not None
    assert flux.parts["initial_mp"] == pytest.approx(0.0264)
    assert flux.parts["additional_mp"] == pytest.approx((2448 * 1632 / 1_048_576 - 1) * 0.0132)
    assert flux.parts["reference_mp"] == pytest.approx(1.5 * 0.0132)
    assert 2 * flux.total * INVOICE_FACTOR == pytest.approx(0.164022, abs=2e-5)
    assert flux.tier == "megapixels/exact/1048576px"
    assert min(astra.total - 0.290049, flare.total - 0.109456, 2 * flux.total - 0.164022) > 0


def test_unknown_deployment_or_missing_table_has_no_price(table: PricingTable) -> None:
    assert estimate_cost(table, "mock-fast_draft_maker", Usage(input_tokens=10)) is None
    assert estimate_cost(None, "gpt-6-luna", Usage(input_tokens=10)) is None


def test_missing_or_invalid_file_returns_none(tmp_path: Path) -> None:
    assert load_pricing(tmp_path / "no-existe.yaml") is None
    invalid = tmp_path / "pricing.yaml"
    invalid.write_text("deployments:\n  x: {type: desconocido}\n", encoding="utf-8")
    assert load_pricing(invalid) is None
