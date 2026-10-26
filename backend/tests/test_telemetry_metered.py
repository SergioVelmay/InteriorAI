import io
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from PIL import Image

from app.foundry import (
    FoundryIncompleteError,
    FoundryUnsupportedError,
    ImageEditRequest,
    ImageRequest,
    InputImage,
    MockFoundryClient,
    TextRequest,
    TextResult,
    Usage,
)
from app.telemetry import request_scope, telemetry_scope
from app.telemetry.metered import MeteredFoundryClient
from app.telemetry.pricing import load_pricing
from shared.models import TelemetryRecord
from shared.roles import Role

PRICING = load_pricing(Path(__file__).resolve().parents[2] / "config" / "pricing.yaml")
REAL_NAMES = {
    Role.PROMPT_ARCHITECT: "gpt-6.1-sol",
    Role.GEOMETRY_AUDITOR: "gpt-6-astra",
    Role.REFERENCE_ANALYST: "gpt-6-luna",
    Role.FAST_DRAFT_MAKER: "gpt-image-2.5-flare",
    Role.COMPOSITION_BUILDER: "gpt-image-2.5-sunburst",
    Role.REALISTIC_RENDERER: "FLUX.2-pro",
}


class MemorySink:
    def __init__(self, fail: bool = False) -> None:
        self.records: list[tuple[UUID, TelemetryRecord]] = []
        self.fail = fail

    async def append_telemetry(self, project_id: UUID, record: TelemetryRecord) -> None:
        if self.fail:
            raise OSError("disco lleno (simulado)")
        self.records.append((project_id, record))


def metered(inner=None, sink=None, pricing=PRICING) -> tuple[MeteredFoundryClient, MemorySink]:
    sink = sink or MemorySink()
    client = MeteredFoundryClient(
        inner=inner or MockFoundryClient(),
        pricing=pricing,
        sink=sink,
        deployment_for=REAL_NAMES.__getitem__,
        simulated=True,
    )
    return client, sink


def png(size: tuple[int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size).save(buffer, "PNG")
    return buffer.getvalue()


async def test_text_call_is_recorded_with_cost_and_context() -> None:
    client, sink = metered()
    project = uuid4()
    with request_scope("req-123"), telemetry_scope(project):
        result = await client.complete_text(Role.GEOMETRY_AUDITOR, TextRequest(input="Audita"))

    [(project_id, record)] = sink.records
    assert project_id == project
    assert record.request_id == "req-123"
    assert record.role is Role.GEOMETRY_AUDITOR
    assert record.deployment == "gpt-6-astra"  # nombre real aunque el cliente sea mock
    assert record.operation == "complete_text"
    assert record.status == "ok"
    assert record.simulated is True
    assert record.output_tokens == result.usage.output_tokens
    assert record.reasoning_tokens == result.usage.reasoning_tokens > 0
    assert record.pricing_tier == "global/short"
    expected = (result.usage.input_tokens * 8.80 + result.usage.output_tokens * 44.0) / 1e6
    expected *= 0.98463  # billing_factor de config/pricing.yaml
    assert record.cost_eur == pytest.approx(expected)


async def test_image_calls_record_megapixels() -> None:
    client, sink = metered()
    with telemetry_scope(uuid4()):
        await client.generate_image(
            Role.REALISTIC_RENDERER, ImageRequest(prompt="x", size="1024x1024")
        )
        await client.edit_image(
            Role.REALISTIC_RENDERER,
            ImageEditRequest(
                prompt="x", size="512x512", images=[InputImage(data=png((1000, 500)))]
            ),
        )
    generated, edited = (record for _, record in sink.records)
    assert generated.images_out == 1
    assert generated.megapixels_out == pytest.approx(1.048576)
    # 1024x1024 = exactamente 1 MP binario (megapixel_px = 2^20): solo el primer MP
    assert generated.cost_eur == pytest.approx(0.0264 * 0.98463)
    assert edited.operation == "edit_image"
    assert edited.megapixels_ref == pytest.approx(0.5)
    assert edited.cost_breakdown["reference_mp"] == pytest.approx(0.0132 * 0.98463)  # 1 MP


async def test_errors_with_usage_are_recorded_and_reraised() -> None:
    class Incomplete(MockFoundryClient):
        async def _complete_text(self, role: Role, request: TextRequest) -> TextResult:
            raise FoundryIncompleteError(
                "incompleta", role=role, usage=Usage(input_tokens=100, output_tokens=2000)
            )

    client, sink = metered(inner=Incomplete())
    with telemetry_scope(uuid4()), pytest.raises(FoundryIncompleteError):
        await client.complete_text(Role.GEOMETRY_AUDITOR, TextRequest(input="x"))
    [(_, record)] = sink.records
    assert record.status == "error"
    assert record.error_type == "FoundryIncompleteError"
    assert record.cost_eur == pytest.approx((100 * 8.80 + 2000 * 44.0) / 1e6 * 0.98463)


async def test_invalid_role_is_rejected_before_any_record() -> None:
    client, sink = metered()
    with telemetry_scope(uuid4()), pytest.raises(FoundryUnsupportedError):
        await client.complete_text(Role.FAST_DRAFT_MAKER, TextRequest(input="x"))
    assert sink.records == []


async def test_without_project_scope_nothing_is_persisted() -> None:
    client, sink = metered()
    await client.complete_text(Role.PROMPT_ARCHITECT, TextRequest(input="x"))
    assert sink.records == []


async def test_sink_failure_does_not_break_the_call() -> None:
    client, _ = metered(sink=MemorySink(fail=True))
    with telemetry_scope(uuid4()):
        result = await client.complete_text(Role.PROMPT_ARCHITECT, TextRequest(input="x"))
    assert result.text


async def test_without_pricing_cost_is_none() -> None:
    client, sink = metered(pricing=None)
    with telemetry_scope(uuid4()):
        await client.complete_text(Role.REFERENCE_ANALYST, TextRequest(input="x"))
    [(_, record)] = sink.records
    assert record.cost_eur is None
    assert record.pricing_tier is None
