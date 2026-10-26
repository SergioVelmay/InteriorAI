import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import PRICING_FILE
from fastapi.testclient import TestClient

from app.foundry import ImageRequest, TextRequest
from app.storage import ProjectRepository
from app.telemetry import telemetry_scope
from app.telemetry.__main__ import main as telemetry_cli
from shared.models import TelemetryRecord
from shared.roles import Role


def create_project(api: TestClient) -> str:
    return api.post("/api/v1/projects", json={"name": "x"}).json()["id"]


# --- X-Request-ID ------------------------------------------------------------------------


def test_request_id_is_generated_and_returned(api: TestClient) -> None:
    response = api.get("/health")
    assert len(response.headers["x-request-id"]) == 32


def test_valid_incoming_request_id_is_kept(api: TestClient) -> None:
    response = api.get("/health", headers={"X-Request-ID": "ui-abc.123"})
    assert response.headers["x-request-id"] == "ui-abc.123"


def test_invalid_incoming_request_id_is_replaced(api: TestClient) -> None:
    response = api.get("/health", headers={"X-Request-ID": "malo\tcon espacios" + "x" * 80})
    assert response.headers["x-request-id"] != "malo"
    assert len(response.headers["x-request-id"]) == 32


def test_request_id_on_error_responses(make_api: Callable[..., TestClient]) -> None:
    api = make_api(max_upload_mb=1)
    response = api.post("/api/v1/projects", content=b"0" * (3 * 1024 * 1024))
    assert response.status_code == 413
    assert "x-request-id" in response.headers


# --- Costes -------------------------------------------------------------------------------


async def _simulate_calls(api: TestClient, project_id: str) -> None:
    client = api.app.state.foundry
    with telemetry_scope(project_id):
        await client.complete_text(Role.PROMPT_ARCHITECT, TextRequest(input="Salón nórdico"))
        await client.complete_text(Role.GEOMETRY_AUDITOR, TextRequest(input="Audita"))
        await client.generate_image(
            Role.REALISTIC_RENDERER, ImageRequest(prompt="x", size="1024x1024")
        )


def test_costs_summary_aggregates(api: TestClient) -> None:
    project_id = create_project(api)
    api.portal.call(_simulate_calls, api, project_id)

    summary = api.get(f"/api/v1/projects/{project_id}/costs").json()
    assert summary["currency"] == "EUR"
    assert summary["estimated"] is True
    assert summary["includes_simulated"] is True
    totals = summary["totals"]
    assert totals["calls"] == 3
    assert totals["errors"] == 0
    assert totals["images_out"] == 1
    assert totals["reasoning_tokens"] > 0
    assert totals["cost_eur"] == pytest.approx(
        sum(g["cost_eur"] for g in summary["by_role"]), abs=1e-6
    )
    assert [g["key"] for g in summary["by_role"]] == [
        "GEOMETRY_AUDITOR",
        "PROMPT_ARCHITECT",
        "REALISTIC_RENDERER",
    ]
    assert len(summary["by_day"]) == 1
    assert {g["key"] for g in summary["by_deployment"]} == {
        "mock-geometry_auditor",
        "mock-realistic_renderer",
        "mock-prompt_architect",
    }  # sin DEPLOYMENT_ROLE_* configurados en el test → sin precio
    # Sin despliegues configurados, cada llamada en su rol guardado y sin despliegue actual
    assert {g["key"]: g["label"] for g in summary["by_role"]} == {
        "GEOMETRY_AUDITOR": None, "PROMPT_ARCHITECT": None, "REALISTIC_RENDERER": None,
    }  # fmt: skip
    [day] = {g["key"] for g in summary["by_day"]}
    assert [(g["key"], g["role"]) for g in summary["by_day_role"]] == [
        (day, "GEOMETRY_AUDITOR"), (day, "PROMPT_ARCHITECT"), (day, "REALISTIC_RENDERER"),
    ]  # fmt: skip
    assert [g["role"] for g in summary["by_project_role"]] == [
        "GEOMETRY_AUDITOR", "PROMPT_ARCHITECT", "REALISTIC_RENDERER",
    ]  # fmt: skip
    assert all(r["call_role"] == r["role"] for r in summary["records"])
    assert totals["unpriced_calls"] == 3
    assert len(summary["records"]) == 3


def test_costs_limit_and_empty_project(api: TestClient) -> None:
    project_id = create_project(api)
    empty = api.get(f"/api/v1/projects/{project_id}/costs").json()
    assert empty["totals"]["calls"] == 0
    assert empty["includes_simulated"] is False

    api.portal.call(_simulate_calls, api, project_id)
    limited = api.get(f"/api/v1/projects/{project_id}/costs", params={"limit": 1}).json()
    assert limited["totals"]["calls"] == 3
    assert len(limited["records"]) == 1


def test_costs_with_configured_deployments_are_priced(
    make_api: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEPLOYMENT_ROLE_PROMPT_ARCHITECT", "gpt-6.1-sol")
    api = make_api()
    project_id = create_project(api)
    api.portal.call(_simulate_calls, api, project_id)
    by_deployment = {
        g["key"]: g for g in api.get(f"/api/v1/projects/{project_id}/costs").json()["by_deployment"]
    }
    assert by_deployment["gpt-6.1-sol"]["unpriced_calls"] == 0
    assert by_deployment["gpt-6.1-sol"]["cost_eur"] > 0


def _stored(role: str, deployment: str, cost: float) -> str:
    """Una línea de telemetría tal como la guardaba la 2.x (rol con el nombre anterior)."""
    return json.dumps({
        "id": str(uuid4()), "timestamp": "2026-10-20T10:00:00Z", "role": role,
        "deployment": deployment, "operation": "complete_text", "status": "ok",
        "latency_s": 1.0, "cost_eur": cost, "simulated": False,
    })  # fmt: skip


def test_costs_go_to_the_current_role_of_each_deployment(
    make_api: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Paso 26 (B-057): cada llamada cuenta en el rol que hoy tiene su despliegue; una serie
    por rol. Las llamadas antiguas con nombres anteriores se leen sin reescribirse."""
    monkeypatch.setenv("DEPLOYMENT_ROLE_PROMPT_ARCHITECT", "gpt-6-luna")
    monkeypatch.setenv("DEPLOYMENT_ROLE_REFERENCE_ANALYST", "gpt-6.1-sol")
    api = make_api()
    project_id = create_project(api)
    log = tmp_path / "data" / project_id / "costes_telemetria.jsonl"
    lines = [
        _stored("PROMPT_ENGINEER", "gpt-6.1-sol", 0.04),  # sol es hoy de REFERENCE_ANALYST
        _stored("REFERENCE_ANALYST", "gpt-6-luna", 0.001),  # luna es hoy de PROMPT_ARCHITECT
        _stored("CONTEXT_MANAGER", "gpt-6.1-sol", 0.03),
        _stored("GEOMETRIC_AUDITOR", "gpt-5-viejo", 0.2),  # despliegue ya no asignado
    ]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    url = f"/api/v1/projects/{project_id}/costs"
    summary = api.get(url, params={"include_simulated": False}).json()
    by_role = {
        g["key"]: (g["label"], g["calls"], round(g["cost_eur"], 4)) for g in summary["by_role"]
    }
    assert by_role == {
        "REFERENCE_ANALYST": ("gpt-6.1-sol", 2, 0.07),
        "PROMPT_ARCHITECT": ("gpt-6-luna", 1, 0.001),
        "GEOMETRY_AUDITOR": (None, 1, 0.2),  # en su rol guardado, con el nombre actual
    }
    assert summary["role_deployments"]["PROMPT_ARCHITECT"] == "gpt-6-luna"
    assert summary["role_deployments"]["FAST_DRAFT_MAKER"] is None  # sin configurar en el test
    assert len(summary["role_deployments"]) == 6
    calls = {(r["role"], r["call_role"]) for r in summary["records"]}
    assert ("REFERENCE_ANALYST", "PROMPT_ARCHITECT") in calls  # el original, renombrado
    assert ("PROMPT_ARCHITECT", "REFERENCE_ANALYST") in calls
    assert ("GEOMETRY_AUDITOR", "GEOMETRY_AUDITOR") in calls
    all_projects = api.get("/api/v1/costs", params={"include_simulated": False}).json()
    assert {g["key"] for g in all_projects["by_role"]} == set(by_role)


def test_shared_deployments_keep_the_stored_role(
    make_api: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEPLOYMENT_ROLE_PROMPT_ARCHITECT", "gpt-6-luna")
    monkeypatch.setenv("DEPLOYMENT_ROLE_REFERENCE_ANALYST", "gpt-6-luna")  # compartido
    api = make_api()
    project_id = create_project(api)
    log = tmp_path / "data" / project_id / "costes_telemetria.jsonl"
    log.write_text(_stored("REFERENCE_ANALYST", "gpt-6-luna", 0.01) + "\n", encoding="utf-8")
    summary = api.get(f"/api/v1/projects/{project_id}/costs").json()
    assert [g["key"] for g in summary["by_role"]] == ["REFERENCE_ANALYST"]


def test_costs_for_missing_project(api: TestClient) -> None:
    assert api.get(f"/api/v1/projects/{uuid4()}/costs").status_code == 404


def _real_record(cost: float, role: Role = Role.FAST_DRAFT_MAKER, **extra) -> TelemetryRecord:
    return TelemetryRecord(
        role=role, deployment="d", operation="generate_image", status="ok", latency_s=1.0,
        cost_eur=cost, simulated=False, **extra,
    )  # fmt: skip


def test_costs_without_simulated_calls_and_for_all_projects(api: TestClient) -> None:
    repo: ProjectRepository = api.app.state.repository
    first = create_project(api)
    second = api.post("/api/v1/projects", json={"name": "Dormitorio"})
    second = second.json()["id"]
    api.portal.call(_simulate_calls, api, first)  # 3 llamadas simuladas
    api.portal.call(repo.append_telemetry, first, _real_record(0.1))
    api.portal.call(repo.append_telemetry, second, _real_record(0.2))

    url = f"/api/v1/projects/{first}/costs"
    assert api.get(url).json()["totals"]["calls"] == 4  # por defecto, todo (compatibilidad)
    real = api.get(url, params={"include_simulated": False}).json()
    assert real["totals"]["calls"] == 1 and real["totals"]["cost_eur"] == 0.1
    assert real["simulated_excluded"] == 3 and real["includes_simulated"] is False
    assert real["records"][0]["project_name"] == "x"
    assert real["project_name"] == "x"

    everything = api.get("/api/v1/costs", params={"include_simulated": False}).json()
    assert everything["project_id"] is None
    assert everything["totals"]["calls"] == 2
    assert everything["totals"]["cost_eur"] == pytest.approx(0.3)
    assert {g["label"]: g["cost_eur"] for g in everything["by_project"]} == {
        "x": 0.1, "Dormitorio": 0.2,
    }  # fmt: skip
    assert api.get("/api/v1/costs").json()["totals"]["calls"] == 5


def test_cost_alerts_use_real_spend_only(
    make_api: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COST_ALERT_TOTAL_EUR", "3.5")
    api = make_api()
    repo: ProjectRepository = api.app.state.repository
    big = create_project(api)
    small = api.post("/api/v1/projects", json={"name": "Baño"})
    small = small.json()["id"]
    for cost in (2.0, 1.2):
        api.portal.call(repo.append_telemetry, big, _real_record(cost))
    api.portal.call(repo.append_telemetry, small, _real_record(0.4))
    api.portal.call(_simulate_calls, api, small)  # lo simulado no cuenta

    alerts = api.get("/api/v1/costs/alerts").json()
    assert [(a["name"], a["cost_eur"], a["exceeded"]) for a in alerts["projects"]] == [
        ("x", 3.2, True), ("Baño", 0.4, False),
    ]  # fmt: skip
    assert alerts["projects"][0]["threshold_eur"] == 3.0  # por defecto
    assert alerts["total"] == {
        "project_id": None, "name": None, "cost_eur": 3.6, "threshold_eur": 3.5,
        "exceeded": True,
    }  # fmt: skip


def test_chain_cost_matches_legacy_briefs_and_references_by_time() -> None:
    from datetime import timedelta

    from app.telemetry.chain import chain_cost
    from shared.models import (
        Asset,
        AssetAnalysis,
        AssetKind,
        DesignBrief,
        DesignBriefContent,
        DimensionsCm,
        ImagePrompts,
        ProjectMetadata,
        ReferenceAnalysis,
        RenderRecord,
        utc_now,
    )  # fmt: skip

    ficha = ReferenceAnalysis(
        category="sofa", item_name="Sofá", brand=None, product_name=None, style_tags=[],
        colors=[], materials=[], dimensions_cm=DimensionsCm(width_cm=None, depth_cm=None,
        height_cm=None), dimensions_source="desconocido", summary="s", design_relevance="d",
    )  # fmt: skip
    reference = Asset(
        kind=AssetKind.REFERENCIA, stored_name="r.png", original_name="r.png",
        mime_type="image/png", size_bytes=1, sha256="0" * 64,
        analysis=AssetAnalysis(result=ficha),  # anterior al Paso 16: sin request_id
    )  # fmt: skip
    content = DesignBriefContent(
        title="t", summary="s", spatial_constraints=[], furniture=[], palette=[], materials=[],
        lighting="l", camera="c", open_questions=[],
        image_prompts=ImagePrompts(fast_draft="f", structural_composer="s",
                                   photorealistic_renderer="p"),
    )  # fmt: skip
    # Anterior al Paso 14: sin request_id
    brief = DesignBrief(version=1, content=content, reference_asset_ids=[reference.id])
    draft = RenderRecord(
        id=uuid4(), stage="boceto", role=Role.FAST_DRAFT_MAKER, deployment="d", brief_id=brief.id,
        brief_version=1, prompt="p", input_asset_ids=[], batch_id=uuid4(), size="1536x1024",
        request_id="r-draft",
    )  # fmt: skip
    now = utc_now()
    project = ProjectMetadata(
        id=uuid4(), name="x", created_at=now, updated_at=now,
        briefs=[brief], renders=[draft], assets=[reference],
    )  # fmt: skip
    analyzed = reference.analysis.analyzed_at
    records = [
        _real_record(0.0004, Role.REFERENCE_ANALYST, request_id="r-ficha",
                     timestamp=analyzed - timedelta(seconds=2)),
        _real_record(0.02, Role.PROMPT_ARCHITECT, request_id="r-brief",
                     timestamp=brief.created_at - timedelta(seconds=1)),
        _real_record(0.5, Role.PROMPT_ARCHITECT, request_id="r-other",
                     timestamp=brief.created_at - timedelta(hours=1)),  # otro brief
        _real_record(0.03, request_id="r-draft"),
        _real_record(0.03, request_id="r-sibling"),  # otra llamada: fuera de la cadena
    ]  # fmt: skip
    result = chain_cost(project, records, draft.id)
    assert result is not None and result.renders == 1
    assert result.briefs == 1 and result.references == 1
    assert result.totals.calls == 3 and result.totals.cost_eur == pytest.approx(0.0504)
    assert chain_cost(project, records, uuid4()) is None


def test_pricing_endpoint(api: TestClient) -> None:
    pricing = api.get("/api/v1/pricing").json()
    assert pricing["long_context_threshold_tokens"] == 272000
    assert pricing["deployments"]["FLUX.2-pro"]["type"] == "megapixels"


def test_pricing_endpoint_without_file(
    make_api: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = make_api()
    api.app.state.foundry.pricing = None
    assert api.get("/api/v1/pricing").status_code == 404


# --- Persistencia concurrente ---------------------------------------------------------------


async def test_concurrent_telemetry_appends_are_not_lost(tmp_path: Path) -> None:
    from shared.models import ProjectCreate

    repo = ProjectRepository(tmp_path / "data")
    await repo.init()
    project = await repo.create(ProjectCreate(name="x"))
    records = [
        TelemetryRecord(
            role=Role.FAST_DRAFT_MAKER,
            deployment="d",
            operation="generate_image",
            status="ok",
            latency_s=0.1,
        )
        for _ in range(30)
    ]
    await asyncio.gather(*(repo.append_telemetry(project.id, r) for r in records))
    log = await repo.read_telemetry(project.id)
    assert {r.id for r in log.records} == {r.id for r in records}


# --- CLI de simulación ----------------------------------------------------------------------


def test_cli_simulate_records_calls(
    api: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    project_id = create_project(api)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRICING_FILE", str(PRICING_FILE))
    monkeypatch.setenv("DEPLOYMENT_ROLE_GEOMETRY_AUDITOR", "gpt-6-astra")
    assert telemetry_cli(["simular", project_id, "--llamadas", "6"]) == 0
    assert "Registros en el proyecto: 6" in capsys.readouterr().out

    summary = api.get(f"/api/v1/projects/{project_id}/costs").json()
    assert summary["totals"]["calls"] == 6
    assert {g["key"] for g in summary["by_role"]} == {role.value for role in Role}
    assert all(r["request_id"].startswith("simulacion-") for r in summary["records"])


def test_cli_simulate_refuses_in_azure_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    for key, value in {
        "AI_PROVIDER_MODE": "azure",
        "AZURE_FOUNDRY_ENDPOINT": "https://example.com",
        "AZURE_FOUNDRY_API_KEY": "fake-key-for-tests-0000",
        "AZURE_FOUNDRY_RENDERER_PATH": "/providers/x/v1/y",
        **{role.env_var: "dep" for role in Role},
    }.items():
        monkeypatch.setenv(key, value)
    assert telemetry_cli(["simular", str(uuid4())]) == 2
    assert "Bloqueado" in capsys.readouterr().out


def test_cli_simulate_unknown_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    assert telemetry_cli(["simular", str(uuid4())]) == 1
    assert telemetry_cli(["simular", "no-es-uuid"]) == 1
