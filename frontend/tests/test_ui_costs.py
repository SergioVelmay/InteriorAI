from pathlib import Path
from uuid import uuid4

import anyio
import gradio as gr
import httpx
import pandas as pd

from ui.api_client import BackendClient
from ui.cost_views import (
    alert_lines,
    chain_cost_md,
    day_role_frame,
    filter_records,
    kpi_html,
    notes_md,
    pricing_frame,
    project_calls_md,
    project_frame,
    records_csv,
    records_frame,
    role_frame,
    y_range,
)
from ui.tabs.costs import ACTIVE, EVERYTHING, build_costs_tab

PROJECT = str(uuid4())


def record(role: str, cost: float | None, day: str = "2026-10-18", **extra) -> dict:
    return {
        "id": str(uuid4()), "timestamp": f"{day}T10:00:00Z", "request_id": "r1", "role": role,
        "deployment": "d", "operation": "edit_image", "status": "ok", "error_type": None,
        "latency_s": 12.34, "input_tokens": 100, "output_tokens": 50, "megapixels_out": 2.4576,
        "cost_eur": cost, "simulated": False, "project_id": PROJECT, "project_name": "Salón",
    } | extra  # fmt: skip


RECORDS = [
    record("PHOTOREALISTIC_RENDERER", 0.0873),
    record("FAST_DRAFT", 0.0305, day="2026-10-17"),
    record("GEOMETRIC_AUDITOR", 0.0, status="error", error_type="FoundryTimeoutError"),
]


def summary(**extra) -> dict:
    return {
        "project_id": PROJECT, "project_name": "Salón", "currency": "EUR", "estimated": True,
        "includes_simulated": False, "simulated_excluded": 0,
        "totals": {"calls": 3, "errors": 1, "unpriced_calls": 0, "cost_eur": 0.1178,
                   "images_out": 2, "megapixels_out": 4.9152, "latency_s": 37.02},
        "by_role": [{"key": "FAST_DRAFT", "cost_eur": 0.0305, "calls": 1},
                    {"key": "PHOTOREALISTIC_RENDERER", "cost_eur": 0.0873, "calls": 1}],
        "by_project": [{"key": PROJECT, "label": "Salón", "cost_eur": 0.1178}],
        "records": RECORDS,
    } | extra  # fmt: skip


PRICING = {
    "deployment_type": "global",
    "deployments": {
        "gpt-6-luna": {"type": "tokens", "rates": {"global": {"short": {
            "input": 0.088, "cached_input": 0.009, "output": 0.44}}}},
        "gpt-image-2.5-flare": {"type": "image_tokens", "input_text": 4.4,
                                "input_image": 7.04, "output_image": 26.4},
        "FLUX.2-pro": {"type": "megapixels", "initial_mp": 0.0264, "additional_mp": 0.0132,
                       "reference_mp": 0.0132},
    },
}  # fmt: skip


# --- Presentación ---------------------------------------------------------------------------


def test_kpis_and_notes() -> None:
    html = kpi_html(summary())
    assert "0.1178 €" in html and "Latencia media" in html and "12.3 s" in html
    notes = notes_md(summary(simulated_excluded=4))
    assert "estimado" in notes and "4 llamada(s) simulada(s) ocultas" in notes
    assert "pudo facturarlas" in notes  # hay un error
    assert "simuladas" in notes_md(summary(includes_simulated=True))


def test_frames_for_the_charts() -> None:
    assert role_frame(summary())["Coste (€)"].tolist() == [0.0305, 0.0873]
    days = day_role_frame(RECORDS)
    assert days.to_dict("records")[0] == {"Día": "2026-10-17", "Rol": "FAST_DRAFT",
                                          "Coste (€)": 0.0305}  # fmt: skip
    assert len(days) == 3
    assert project_frame(summary())["Proyecto"].tolist() == ["Salón"]
    assert role_frame(summary(by_role=[])).empty
    assert y_range(project_frame(summary())) == [0.0, 0.13547]
    assert y_range(role_frame(summary(by_role=[]))) == [0.0, 0.01]


def test_records_table_filters_and_csv() -> None:
    assert len(filter_records(RECORDS, "Todos", "error")) == 1
    assert len(filter_records(RECORDS, "FAST_DRAFT", "Todos")) == 1
    frame = records_frame(RECORDS)
    assert isinstance(frame, pd.DataFrame) and len(frame) == 3
    assert frame.iloc[2]["Estado"] == "error (FoundryTimeoutError)"
    assert frame.iloc[0]["Fecha (UTC)"] == "2026-10-18 10:00:00"
    assert "Proyecto" not in records_frame(RECORDS, with_project=False).columns
    text = records_csv(RECORDS)
    assert text.splitlines()[0].startswith("Fecha (UTC);Proyecto;Rol")
    assert ";PHOTOREALISTIC_RENDERER;" in text.splitlines()[1]


def test_pricing_and_chain_cost() -> None:
    frame = pricing_frame(PRICING)
    assert frame["Despliegue"].tolist() == ["gpt-6-luna", "gpt-image-2.5-flare", "FLUX.2-pro"]
    assert (
        "salida 0.44" in frame.iloc[0]["Tarifas"]
        and "MP adicional 0.0132" in frame.iloc[2]["Tarifas"]
    )
    assert pricing_frame(None).empty
    line = chain_cost_md({"totals": {"cost_eur": 0.2969, "calls": 6}, "simulated_calls": 2})
    assert "0.2969 €" in line and "6 llamada(s)" in line and "simulación: 2" in line
    assert chain_cost_md(None) == ""


# --- Cliente y pestaña --------------------------------------------------------------------------


def fake_client(seen: list[httpx.Request]) -> BackendClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/pricing":
            return httpx.Response(200, json=PRICING)
        if request.url.path.endswith("/cost"):
            return httpx.Response(200, json={"totals": {"cost_eur": 0.1}})
        if request.url.path == "/api/v1/costs/alerts":
            return httpx.Response(200, json=ALERTS)
        if request.url.path == "/api/v1/costs":
            return httpx.Response(200, json=summary(project_id=None))
        return httpx.Response(200, json=summary())

    return BackendClient("http://backend.test", transport=httpx.MockTransport(handler))


async def test_cost_client_requests() -> None:
    seen: list[httpx.Request] = []
    client = fake_client(seen)
    await client.costs(PROJECT)
    await client.costs(None, include_simulated=True, limit=10)
    await client.render_cost(PROJECT, "r")
    assert (await client.pricing())["deployment_type"] == "global"
    assert [r.url.path for r in seen] == [
        f"/api/v1/projects/{PROJECT}/costs", "/api/v1/costs",
        f"/api/v1/projects/{PROJECT}/renders/r/cost", "/api/v1/pricing",
    ]  # fmt: skip
    assert seen[0].url.params["include_simulated"] == "false"
    assert seen[1].url.params["include_simulated"] == "true" and seen[1].url.params["limit"] == "10"


def build(seen: list[httpx.Request]):
    with gr.Blocks():
        active = gr.BrowserState(None)
        tab = build_costs_tab(fake_client(seen), active)
    return tab


def by_id(result: dict, elem_id: str):
    return next(v for k, v in result.items() if k.elem_id == elem_id)


async def test_costs_tab_scopes(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    tab = build(seen)

    assert "Ningún proyecto activo" in (await tab.refresh_all(None))[tab.all_outputs[0]]
    assert seen == []  # sin proyecto no se consulta nada

    result = await tab.refresh_all(PROJECT)
    assert result[tab.all_outputs[0]] == "### Costes de IA de «Salón»"
    assert by_id(result, "iai-cost-project")["visible"] is False
    assert len(by_id(result, "iai-cost-table")) == 3
    csv_path = anyio.Path(by_id(result, "iai-cost-csv")["value"])
    assert (await csv_path.read_text(encoding="utf-8-sig")).count("\n") == 4  # cabecera + 3

    result = await tab.load(PROJECT, EVERYTHING, True, "Todos", "error")
    assert result[tab.all_outputs[0]] == "### Costes de IA de todos los proyectos"
    assert by_id(result, "iai-cost-project")["visible"] is True
    assert len(by_id(result, "iai-cost-table")) == 1  # filtro de estado
    assert "/api/v1/costs" in [r.url.path for r in seen]
    assert "Proyectos por encima de 3 €" in result[tab.all_outputs[2]]  # aviso en las notas
    assert ACTIVE != EVERYTHING


ALERTS = {
    "currency": "EUR",
    "total": {"project_id": None, "name": None, "cost_eur": 10.4, "threshold_eur": 10.0,
              "exceeded": True},
    "projects": [
        {"project_id": PROJECT, "name": "Salón", "cost_eur": 3.2, "threshold_eur": 3.0,
         "exceeded": True},
        {"project_id": "otro", "name": "Baño", "cost_eur": 0.4, "threshold_eur": 3.0,
         "exceeded": False},
    ],
}  # fmt: skip


def test_alert_lines() -> None:
    assert alert_lines(None, PROJECT) == []
    project = alert_lines(ALERTS, PROJECT)
    assert project == [
        "⚠️ Este proyecto lleva 3.20 € de IA (aviso a partir de 3 €).",
        "⚠️ El gasto total de IA es 10.40 € (aviso a partir de 10 €).",
    ]
    assert alert_lines(ALERTS, "otro") == project[1:]  # el otro proyecto no lo supera
    everything = alert_lines(ALERTS, None)
    assert everything[0] == "⚠️ Proyectos por encima de 3 €: Salón (3.20 €)."
    calm = {**ALERTS, "total": {**ALERTS["total"], "exceeded": False}}
    assert alert_lines(calm, "otro") == []


async def test_cost_alerts_client_never_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "caído"})

    client = BackendClient("http://backend.test", transport=httpx.MockTransport(handler))
    assert await client.cost_alerts() is None  # un aviso nunca impide usar la app


def test_project_calls_md_is_compact() -> None:
    """B-027: las llamadas en el resumen del proyecto, con lo esencial."""
    records = [
        {"timestamp": "2026-10-24T22:48:19.123Z", "role": "PROMPT_ENGINEER", "status": "ok",
         "simulated": True, "cost_eur": 0.00107},
        {"timestamp": "2026-10-24T09:13:19Z", "role": "PHOTOREALISTIC_RENDERER",
         "status": "error", "simulated": False, "cost_eur": None},
    ]  # fmt: skip
    lines = project_calls_md(records).splitlines()
    assert lines[0] == "| Fecha (UTC) | Rol | Estado | Coste (€) |"
    assert lines[2] == "| 24/10/26 22:48 | PROMPT_ENGINEER | ✓ (sim.) | 0.0011 |"
    assert lines[3] == "| 24/10/26 09:13 | PHOTOREALISTIC_RENDERER | error | — |"
    assert project_calls_md([]) == "_Sin llamadas de IA._"
