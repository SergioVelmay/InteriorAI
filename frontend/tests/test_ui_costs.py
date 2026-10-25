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
    day_chart,
    day_frame,
    filter_records,
    kpi_html,
    notes_md,
    pricing_frame,
    project_calls_md,
    project_chart,
    record_detail_md,
    records_csv,
    records_frame,
    role_chart,
    role_frame,
    series_colors,
)
from ui.tabs.costs import ACTIVE, EVERYTHING, build_costs_tab

PROJECT = str(uuid4())


def record(role: str, cost: float | None, day: str = "2026-10-18", **extra) -> dict:
    return {
        "id": str(uuid4()), "timestamp": f"{day}T10:00:00Z", "request_id": "r1", "role": role,
        "deployment": "d", "operation": "edit_image", "status": "ok", "error_type": None,
        "latency_s": 12.34, "input_tokens": 100, "cached_input_tokens": 20,
        "output_tokens": 50, "reasoning_tokens": 7, "megapixels_out": 2.4576,
        "megapixels_ref": 1.0, "images_out": 1, "cost_eur": cost, "cost_breakdown":
        {"output": 0.08}, "pricing_tier": "global", "simulated": False, "project_id": PROJECT,
        "project_name": "Salón",
    } | extra  # fmt: skip


RECORDS = [
    record("PHOTOREALISTIC_RENDERER", 0.0873, deployment="FLUX.2-pro"),
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
        "by_role_deployment": [
            {"key": "FAST_DRAFT (d)", "label": "FAST_DRAFT", "cost_eur": 0.0305, "calls": 1},
            {"key": "PHOTOREALISTIC_RENDERER (FLUX.2-pro)", "label": "PHOTOREALISTIC_RENDERER",
             "cost_eur": 0.0873, "calls": 1}],
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
    notes = notes_md(summary())
    assert "Gasto **real**" in notes and "estimado" in notes
    assert "pudo facturarlas" in notes  # hay un error
    empty = summary(totals=summary()["totals"] | {"calls": 0, "errors": 0})
    assert "Todavía no hay llamadas reales" in notes_md(empty)


def test_series_colors_follow_the_role() -> None:
    colors = series_colors({
        "PROMPT_ENGINEER (gpt-6-luna)": "PROMPT_ENGINEER",
        "PROMPT_ENGINEER (gpt-6.1-sol)": "PROMPT_ENGINEER",
        "FAST_DRAFT (flare)": "FAST_DRAFT",
    })  # fmt: skip
    assert colors["FAST_DRAFT (flare)"] == "#38bdf8"
    assert colors["PROMPT_ENGINEER (gpt-6-luna)"] == "#a1a1aa"
    assert colors["PROMPT_ENGINEER (gpt-6.1-sol)"] not in {"#a1a1aa", "#38bdf8"}  # más claro


def test_charts_have_a_full_legend_and_readable_labels() -> None:
    """B-032: leyenda «rol (despliegue)», una por línea y sin recortar; rol en dos líneas."""
    spec = role_chart(summary()).to_dict()
    legend = spec["encoding"]["color"]["legend"]
    assert legend["columns"] == 1 and legend["labelLimit"] == 0 and legend["orient"] == "bottom"
    assert spec["encoding"]["color"]["scale"]["domain"] == [
        "FAST_DRAFT (d)", "PHOTOREALISTIC_RENDERER (FLUX.2-pro)",
    ]  # fmt: skip
    assert "split(datum.label" in spec["encoding"]["x"]["axis"]["labelExpr"]
    assert role_frame(summary(by_role_deployment=[])).empty

    days = day_frame(RECORDS)
    assert days.to_dict("records")[0] == {
        "Día": "2026-10-17", "Serie": "FAST_DRAFT (d)", "Rol": "FAST_DRAFT", "Coste (€)": 0.0305,
    }  # fmt: skip
    assert day_chart(RECORDS).to_dict()["encoding"]["x"]["axis"]["labelAngle"] == 0  # caben
    many = [record("FAST_DRAFT", 0.01, day=f"2026-10-{d:02d}") for d in range(1, 20)]
    assert day_chart(many).to_dict()["encoding"]["x"]["axis"]["labelAngle"] == -40  # giradas

    projects = summary(by_project=[{"key": str(i), "label": f"Proyecto con nombre largo {i}",
                                    "cost_eur": 0.1} for i in range(5)])  # fmt: skip
    assert project_chart(projects).to_dict()["encoding"]["x"]["axis"]["labelAngle"] == -40
    assert project_chart(summary()).to_dict()["encoding"]["x"]["axis"]["labelAngle"] == 0


def test_records_table_detail_and_csv() -> None:
    """B-033: tabla con despliegue y MPx, sin simulada ni petición; el resto en el detalle."""
    assert len(filter_records(RECORDS, "Todos", "error")) == 1
    assert len(filter_records(RECORDS, "FAST_DRAFT", "Todos")) == 1
    frame = records_frame(RECORDS)
    assert isinstance(frame, pd.DataFrame) and len(frame) == 3
    assert list(frame.columns) == [
        "Fecha (UTC)", "Proyecto", "Rol", "Despliegue", "Estado", "Coste (€)", "Latencia (s)",
        "Tokens entrada", "Tokens salida", "MPx generados", "MPx referencia",
    ]  # fmt: skip
    assert frame.iloc[2]["Estado"] == "error"  # sin el error concreto
    assert frame.iloc[0]["Estado"] == "✓"
    assert frame.iloc[0]["Despliegue"] == "FLUX.2-pro"
    assert frame.iloc[0]["MPx referencia"] == 1.0
    assert "Proyecto" not in records_frame(RECORDS, with_project=False).columns

    detail = record_detail_md(RECORDS[2])
    assert "`FoundryTimeoutError`" in detail and "`edit_image`" in detail
    assert "en caché 20" in detail and "razonamiento 7" in detail and "`r1`" in detail
    assert "Selecciona una fila" in record_detail_md(None)

    lines = records_csv(RECORDS).splitlines()
    header = lines[0].split(";")
    assert header[:4] == ["Fecha (UTC)", "Proyecto", "Rol", "Despliegue"]
    assert {"Error", "Petición", "Tokens en caché", "Desglose del coste"} <= set(header)
    assert "FoundryTimeoutError" in lines[3] and len(lines) == 4


def test_pricing_rates_in_columns_with_units() -> None:
    """B-034: tres tarifas en columnas y las unidades aparte (MPx para megapíxeles)."""
    frame = pricing_frame(PRICING)
    assert list(frame.columns) == [
        "Despliegue", "Tipo", "Tarifa 1", "Tarifa 2", "Tarifa 3", "Unidades",
    ]  # fmt: skip
    assert frame.iloc[0][["Tarifa 1", "Tarifa 3", "Unidades"]].tolist() == [
        "entrada 0,088", "salida 0,44", "€/M tokens",
    ]  # fmt: skip
    assert frame.iloc[2][["Tarifa 2", "Unidades"]].tolist() == ["MPx adicional 0,0132", "€/MPx"]
    assert pricing_frame(None).empty


def test_chain_cost_line() -> None:
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

    assert "Ningún proyecto activo" in by_id(await tab.refresh_all(None), "iai-cost-notes")
    assert seen == []  # sin proyecto no se consulta nada

    result = await tab.refresh_all(PROJECT)
    assert all(r.url.params.get("include_simulated", "false") == "false" for r in seen)  # B-031
    assert by_id(result, "iai-cost-project")["visible"] is False
    assert by_id(result, "iai-cost-role").to_dict()["mark"]["type"] == "bar"
    assert len(by_id(result, "iai-cost-table")["value"]) == 3
    csv_path = anyio.Path(by_id(result, "iai-cost-csv")["value"])
    assert (await csv_path.read_text(encoding="utf-8-sig")).count("\n") == 4  # cabecera + 3

    result = await tab.load(PROJECT, EVERYTHING, "Todos", "error")
    assert by_id(result, "iai-cost-project")["visible"] is True
    assert len(by_id(result, "iai-cost-table")["value"]) == 1  # filtro de estado
    assert "/api/v1/costs" in [r.url.path for r in seen]
    assert "Proyectos por encima de 3 €" in by_id(result, "iai-cost-notes")  # aviso
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
    assert lines[2] == "| 24/10/26 22:48 | PROMPT_ENGINEER | ✓ | 0.0011 |"
    assert lines[3] == "| 24/10/26 09:13 | PHOTOREALISTIC_RENDERER | error | — |"
    assert project_calls_md([]) == "_Sin llamadas reales de IA._"
