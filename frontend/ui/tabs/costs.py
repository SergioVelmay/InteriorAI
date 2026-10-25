"""Pestaña Costes IA: el gasto real en IA del proyecto activo o de todos los proyectos.

Indicadores, coste por rol y despliegue, por día y por proyecto (Altair, B-032), registro de
llamadas con filtros, detalle de la fila seleccionada y descarga en CSV (B-033), y la tabla de
precios vigente (B-034). Solo gasto real: las llamadas simuladas del modo mock no cuentan
(B-031).
"""

from __future__ import annotations

import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gradio as gr

from shared.roles import Role
from ui.api_client import ApiError, BackendClient
from ui.cost_views import (
    ALL,
    alert_lines,
    column_widths,
    day_chart,
    filter_records,
    kpi_html,
    notes_md,
    pricing_frame,
    project_chart,
    record_detail_md,
    records_csv,
    records_frame,
    role_chart,
)

ACTIVE, EVERYTHING = "Proyecto activo", "Todos los proyectos"
NO_PROJECT = "Ningún proyecto activo: elige uno en **Proyectos** o mira **todos los proyectos**."
MAX_RECORDS = 1000


@dataclass
class CostsTab:
    refresh_all: Callable[[str | None], Awaitable[dict]]
    all_outputs: list[gr.components.Component]
    load: Callable[..., Awaitable[dict]]  # con el alcance y los filtros elegidos
    inputs: list[gr.components.Component]


def build_costs_tab(client: BackendClient, active: gr.BrowserState) -> CostsTab:
    records_state = gr.State([])  # todas las llamadas cargadas
    shown_state = gr.State([])  # las que muestra la tabla (tras los filtros), en su orden
    all_projects = gr.State(False)
    with gr.Row(equal_height=True):
        scope = gr.Radio(
            [ACTIVE, EVERYTHING], value=ACTIVE, label="Alcance", elem_id="iai-cost-scope"
        )
        refresh = gr.Button("Actualizar", variant="secondary", scale=0)
    kpis = gr.HTML()
    notes = gr.Markdown(elem_classes="iai-muted", elem_id="iai-cost-notes")
    with gr.Row():
        by_role = gr.Plot(show_label=False, elem_id="iai-cost-role")
        by_day = gr.Plot(show_label=False, elem_id="iai-cost-day")
    by_project = gr.Plot(show_label=False, visible=False, elem_id="iai-cost-project")
    with gr.Accordion("Registro de llamadas", open=True):
        with gr.Row(equal_height=True):
            role_filter = gr.Dropdown(
                [ALL, *(r.value for r in Role)], value=ALL, label="Rol", elem_id="iai-cost-role-f"
            )
            status_filter = gr.Dropdown([ALL, "ok", "error"], value=ALL, label="Estado")
            download = gr.DownloadButton(
                "Descargar CSV", variant="secondary", elem_id="iai-cost-csv"
            )
        table = gr.Dataframe(
            interactive=False,
            wrap=True,
            max_height=480,
            column_widths=column_widths(False),
            elem_id="iai-cost-table",
        )
        detail = gr.Markdown(record_detail_md(None), elem_id="iai-cost-detail")
    with gr.Accordion("Precios vigentes (config/pricing.yaml)", open=False):
        pricing = gr.Dataframe(interactive=False, wrap=False, elem_id="iai-cost-pricing")

    outputs: list[gr.components.Component] = [
        kpis, notes, by_role, by_day, by_project, records_state, shown_state, all_projects,
        table, detail, download, pricing,
    ]  # fmt: skip

    def empty(message: str) -> dict:
        return {
            kpis: "", notes: message, by_role: None, by_day: None,
            by_project: gr.update(visible=False), records_state: [], shown_state: [],
            all_projects: False, table: None, detail: record_detail_md(None),
            download: gr.update(value=None, interactive=False), pricing: gr.skip(),
        }  # fmt: skip

    def table_updates(
        records: list[dict[str, Any]], role: str, status: str, with_project: bool
    ) -> dict:
        shown = filter_records(records, role, status)
        path = None
        if shown:
            handle, name = tempfile.mkstemp(prefix="interiorai-costes-", suffix=".csv")
            with open(handle, "w", encoding="utf-8-sig", newline="") as file:
                file.write(records_csv(shown))
            path = Path(name)
        return {
            shown_state: shown,
            table: gr.update(
                value=records_frame(shown, with_project),
                column_widths=column_widths(with_project),
            ),
            detail: record_detail_md(None),
            download: gr.update(value=str(path) if path else None, interactive=bool(path)),
        }

    async def load(active_id: str | None, chosen_scope: str, role: str, status: str) -> dict:
        project_id = active_id if chosen_scope == ACTIVE else None
        if chosen_scope == ACTIVE and not active_id:
            return empty(NO_PROJECT)
        try:
            summary = await client.costs(project_id, include_simulated=False, limit=MAX_RECORDS)
            prices = await client.pricing()
        except ApiError as exc:
            gr.Warning(exc.detail)
            return empty(f"Costes no disponibles: {exc.detail}")
        records = summary["records"]
        return {
            kpis: kpi_html(summary),
            notes: " ".join(
                [*alert_lines(await client.cost_alerts(), project_id), notes_md(summary)]
            ),
            by_role: role_chart(summary),
            by_day: day_chart(records),
            by_project: gr.update(value=project_chart(summary), visible=project_id is None),
            records_state: records,
            all_projects: project_id is None,
            pricing: pricing_frame(prices),
            **table_updates(records, role, status, project_id is None),
        }

    inputs = [active, scope, role_filter, status_filter]
    for trigger in (scope.change, refresh.click):
        trigger(load, inputs=inputs, outputs=outputs)

    def on_filter(
        records: list[dict[str, Any]], role: str, status: str, with_project: bool
    ) -> dict:
        return table_updates(records, role, status, with_project)

    for dropdown in (role_filter, status_filter):
        dropdown.change(
            on_filter,
            inputs=[records_state, role_filter, status_filter, all_projects],
            outputs=[shown_state, table, detail, download],
        )

    def on_row(evt: gr.SelectData, shown: list[dict[str, Any]]) -> str:
        """«Ver más» (B-033): el detalle de la llamada de la fila seleccionada."""
        row = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        return record_detail_md(shown[row] if 0 <= row < len(shown) else None)

    table.select(on_row, inputs=shown_state, outputs=detail)

    async def refresh_all(active_id: str | None) -> dict:
        return await load(active_id, ACTIVE, ALL, ALL)

    return CostsTab(refresh_all, outputs, load, inputs)
