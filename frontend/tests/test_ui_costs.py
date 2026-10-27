from pathlib import Path
from uuid import uuid4

import anyio
import gradio as gr
import httpx
import pandas as pd

from ui.api_client import BackendClient
from ui.cost_views import (
    ROLE_COLORS,
    alert_lines,
    chain_cost_md,
    day_chart,
    day_frame,
    filter_records,
    kpi_html,
    legend_html,
    notes_md,
    pricing_frame,
    project_calls_md,
    project_chart,
    project_frame,
    record_detail_md,
    records_csv,
    records_frame,
    role_chart,
    role_frame,
)
from ui.tabs.costs import ACTIVE, EVERYTHING, build_costs_tab
from ui.theme import FORCE_DARK_JS

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
    record("REALISTIC_RENDERER", 0.0873, deployment="FLUX.2-pro"),
    record("FAST_DRAFT_MAKER", 0.0305, day="2026-10-17"),
    record("GEOMETRY_AUDITOR", 0.0, status="error", error_type="FoundryTimeoutError"),
]


def summary(**extra) -> dict:
    return {
        "project_id": PROJECT, "project_name": "Salón", "currency": "EUR", "estimated": True,
        "includes_simulated": False, "simulated_excluded": 0,
        "totals": {"calls": 3, "errors": 1, "unpriced_calls": 0, "cost_eur": 0.1178,
                   "images_out": 2, "megapixels_out": 4.9152, "latency_s": 37.02},
        "by_role": [{"key": "FAST_DRAFT_MAKER", "label": "d", "cost_eur": 0.0305, "calls": 1},
                    {"key": "REALISTIC_RENDERER", "label": "FLUX.2-pro", "cost_eur": 0.0873,
                     "calls": 1}],
        "role_deployments": {"REFERENCE_ANALYST": "gpt-6.1-sol", "PROMPT_ARCHITECT": "gpt-6-luna",
                             "FAST_DRAFT_MAKER": "d", "COMPOSITION_BUILDER": None,
                             "REALISTIC_RENDERER": "FLUX.2-pro", "GEOMETRY_AUDITOR": None},
        "by_project": [{"key": PROJECT, "label": "Salón", "cost_eur": 0.1178}],
        "by_day_role": [
            {"key": "2026-10-17", "role": "FAST_DRAFT_MAKER", "cost_eur": 0.0305, "calls": 1},
            {"key": "2026-10-18", "role": "REALISTIC_RENDERER", "cost_eur": 0.0873, "calls": 1},
            {"key": "2026-10-18", "role": "GEOMETRY_AUDITOR", "cost_eur": 0.0, "calls": 1}],
        "by_project_role": [
            {"key": PROJECT, "label": "Salón", "role": "FAST_DRAFT_MAKER", "cost_eur": 0.0305,
             "calls": 1},
            {"key": PROJECT, "label": "Salón", "role": "REALISTIC_RENDERER", "cost_eur": 0.0873,
             "calls": 1}],
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
    assert "solo con lo que se conoce" in notes and "pudo facturar más" in notes  # B-105
    empty = summary(totals=summary()["totals"] | {"calls": 0, "errors": 0})
    assert "Todavía no hay llamadas reales" in notes_md(empty)


def test_six_vivid_role_colors_and_a_common_legend() -> None:
    """B-080 y B-081: un color por rol, distinto y vivo; una sola leyenda, fuera de los gráficos,
    con el despliegue actual de cada rol."""
    assert list(ROLE_COLORS) == [  # B-093: los de texto y después los de imagen
        "REFERENCE_ANALYST", "PROMPT_ARCHITECT", "GEOMETRY_AUDITOR", "FAST_DRAFT_MAKER",
        "COMPOSITION_BUILDER", "REALISTIC_RENDERER",
    ]  # fmt: skip
    assert list(ROLE_COLORS.values()) == [  # verde, morado, azul; amarillo, naranja, rojo
        "#22c55e", "#a855f7", "#3b82f6", "#facc15", "#f97316", "#ef4444",
    ]  # fmt: skip
    assert len(set(ROLE_COLORS.values())) == 6
    legend = legend_html(summary())
    assert legend.count("<li>") == 6
    assert "<strong>PROMPT_ARCHITECT</strong> <span>(gpt-6-luna)</span>" in legend
    assert "<strong>COMPOSITION_BUILDER</strong></li>" in legend  # sin despliegue configurado
    for chart in (role_chart(summary()), day_chart(summary()), project_chart(summary())):
        color = chart.to_dict()["encoding"]["color"]
        assert color["legend"] is None  # la leyenda es la común
        assert color["scale"]["domain"] == list(ROLE_COLORS)  # mismos colores en todos


def test_charts_by_role_day_and_project() -> None:
    spec = role_chart(summary()).to_dict()
    assert spec["encoding"]["x"]["sort"] == list(ROLE_COLORS)
    assert role_frame(summary(by_role=[])).empty

    days = day_frame(summary())
    assert days.to_dict("records")[0] == {
        "Día": "2026-10-17", "Rol": "FAST_DRAFT_MAKER", "Coste (€)": 0.0305, "Llamadas": 1,
    }  # fmt: skip
    spec = day_chart(summary()).to_dict()
    assert spec["encoding"]["y"]["field"] == "Coste (€)" and spec["mark"]["type"] == "bar"
    assert spec["width"] == 1160  # ancho completo (B-081)
    assert spec["encoding"]["x"]["axis"]["labelAngle"] == 0
    many = summary(by_day_role=[{"key": f"2026-10-{d:02d}", "role": "FAST_DRAFT_MAKER",
                                 "cost_eur": 0.01, "calls": 1} for d in range(1, 31)])  # fmt: skip
    assert day_chart(many).to_dict()["encoding"]["x"]["axis"]["labelAngle"] == -40

    frame = project_frame(summary())
    assert list(frame["Rol"]) == ["FAST_DRAFT_MAKER", "REALISTIC_RENDERER"]  # apilado por rol
    assert set(frame["Proyecto"]) == {"Salón"}
    assert project_chart(summary()).to_dict()["width"] == 1160


def test_records_table_detail_and_csv() -> None:
    """B-033: tabla con despliegue y MPx, sin simulada ni petición; el resto en el detalle."""
    assert len(filter_records(RECORDS, "Todos", "error")) == 1
    assert len(filter_records(RECORDS, "FAST_DRAFT_MAKER", "Todos")) == 1
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

    # Rol actual del despliegue; el original de la llamada, en el detalle y en el CSV (Paso 26)
    moved = record("REFERENCE_ANALYST", 0.04, deployment="gpt-6.1-sol",
                   call_role="PROMPT_ARCHITECT")  # fmt: skip
    assert "**Rol en la llamada:** PROMPT_ARCHITECT" in record_detail_md(moved)
    assert "Rol en la llamada" not in record_detail_md(RECORDS[0])
    assert records_csv([moved]).splitlines()[1].split(";")[2:5] == [
        "REFERENCE_ANALYST", "PROMPT_ARCHITECT", "gpt-6.1-sol",
    ]  # fmt: skip

    lines = records_csv(RECORDS).splitlines()
    header = lines[0].split(";")
    assert header[:5] == ["Fecha (UTC)", "Proyecto", "Rol", "Rol en la llamada", "Despliegue"]
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
    assert "brief" not in line  # B-076: la v3 no tiene brief
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
    assert "Rol (despliegue actual)" in by_id(result, "iai-cost-legend")
    assert len(by_id(result, "iai-cost-table")["value"]) == 3
    csv_path = anyio.Path(by_id(result, "iai-cost-csv")["value"])
    assert (await csv_path.read_text(encoding="utf-8-sig")).count("\n") == 4  # cabecera + 3

    result = await tab.load(PROJECT, EVERYTHING, "Todos", "error")
    assert by_id(result, "iai-cost-project")["visible"] is True
    assert len(by_id(result, "iai-cost-table")["value"]) == 1  # filtro de estado
    assert "/api/v1/costs" in [r.url.path for r in seen]
    assert "Proyectos por encima de 3 €" in by_id(result, "iai-cost-notes")  # aviso
    assert ACTIVE != EVERYTHING


def test_detail_resets_when_clicking_outside_the_table() -> None:
    """B-106: el JS común pulsa el botón oculto, que devuelve el detalle a su estado inicial."""
    with gr.Blocks() as demo:
        active = gr.BrowserState(None)
        build_costs_tab(fake_client([]), active)
    reset = next(b for b in demo.blocks.values() if b.elem_id == "iai-cost-detail-reset")
    assert "iai-hidden" in reset.elem_classes
    for elem_id in ("#iai-cost-detail-reset", "#iai-cost-table", "#iai-cost-detail"):
        assert elem_id in FORCE_DARK_JS
    assert "Selecciona una fila del registro" in FORCE_DARK_JS  # el texto inicial no se oculta
    assert "Selecciona una fila del registro" in record_detail_md(None)
    fn = next(f for f in demo.fns.values() if reset._id in [t[0] for t in f.targets])
    assert fn.fn() == record_detail_md(None)


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
        {"timestamp": "2026-10-24T22:48:19.123Z", "role": "PROMPT_ARCHITECT", "status": "ok",
         "simulated": True, "cost_eur": 0.00107},
        {"timestamp": "2026-10-24T09:13:19Z", "role": "REALISTIC_RENDERER",
         "status": "error", "simulated": False, "cost_eur": None},
    ]  # fmt: skip
    lines = project_calls_md(records).splitlines()
    assert lines[0] == "| Fecha (UTC) | Rol | Estado | Coste (€) |"
    assert lines[2] == "| 24/10/26 22:48 | PROMPT_ARCHITECT | ✓ | 0.0011 |"
    assert lines[3] == "| 24/10/26 09:13 | REALISTIC_RENDERER | error | — |"
    assert project_calls_md([]) == "_Sin llamadas reales de IA._"
