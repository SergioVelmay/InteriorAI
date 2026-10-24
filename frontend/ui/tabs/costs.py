"""Pestaña Costes: lo que cuesta la IA, del proyecto activo o de todos los proyectos.

Indicadores, coste por rol, por día (apilado por rol) y por proyecto, registro de llamadas con
filtros y descarga en CSV, y la tabla de precios vigente. Por defecto, sin las llamadas
simuladas (modo mock).
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
    ROLE_COLORS,
    alert_lines,
    day_role_frame,
    filter_records,
    kpi_html,
    notes_md,
    pricing_frame,
    project_frame,
    records_csv,
    records_frame,
    role_frame,
    y_range,
)

ACTIVE, EVERYTHING = "Proyecto activo", "Todos los proyectos"
NO_PROJECT = "### Ningún proyecto activo\nElige un proyecto en **Proyectos** o mira **todos**."
MAX_RECORDS = 1000


@dataclass
class CostsTab:
    refresh_all: Callable[[str | None], Awaitable[dict]]
    all_outputs: list[gr.components.Component]
    load: Callable[..., Awaitable[dict]]  # con el alcance y los filtros elegidos
    inputs: list[gr.components.Component]


def build_costs_tab(client: BackendClient, active: gr.BrowserState) -> CostsTab:
    records_state = gr.State([])
    all_projects = gr.State(False)
    heading = gr.Markdown()
    with gr.Row(equal_height=True):
        scope = gr.Radio(
            [ACTIVE, EVERYTHING], value=ACTIVE, label="Alcance", elem_id="iai-cost-scope"
        )
        include_simulated = gr.Checkbox(
            value=False, label="Incluir simulación (modo mock)", elem_id="iai-cost-sim"
        )
        refresh = gr.Button("Actualizar", variant="secondary", scale=0)
    kpis = gr.HTML()
    notes = gr.Markdown(elem_classes="iai-muted")
    with gr.Row():
        by_role = gr.BarPlot(
            x="Rol", y="Coste (€)", color="Rol", color_map=ROLE_COLORS, title="Coste por rol",
            x_label_angle=-30, height=300, elem_id="iai-cost-role",
        )  # fmt: skip
        by_day = gr.BarPlot(
            x="Día", y="Coste (€)", color="Rol", color_map=ROLE_COLORS,
            title="Coste por día (apilado por rol)", height=300, elem_id="iai-cost-day",
        )  # fmt: skip
    by_project = gr.BarPlot(
        x="Proyecto", y="Coste (€)", title="Coste por proyecto", height=260, visible=False,
        elem_id="iai-cost-project",
    )  # fmt: skip
    with gr.Accordion("Registro de llamadas", open=True):
        with gr.Row(equal_height=True):
            role_filter = gr.Dropdown(
                [ALL, *(r.value for r in Role)], value=ALL, label="Rol", elem_id="iai-cost-role-f"
            )
            status_filter = gr.Dropdown([ALL, "ok", "error"], value=ALL, label="Estado")
            download = gr.DownloadButton(
                "Descargar CSV", variant="secondary", elem_id="iai-cost-csv"
            )
        table = gr.Dataframe(interactive=False, wrap=True, max_height=480, elem_id="iai-cost-table")
    with gr.Accordion("Precios vigentes (config/pricing.yaml)", open=False):
        pricing = gr.Dataframe(interactive=False, wrap=True)

    outputs: list[gr.components.Component] = [
        heading, kpis, notes, by_role, by_day, by_project, records_state, all_projects, table,
        download, pricing,
    ]  # fmt: skip

    def empty(message: str) -> dict:
        return {
            heading: message, kpis: "", notes: "", by_role: None, by_day: None,
            by_project: gr.update(visible=False), records_state: [], all_projects: False,
            table: None,
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
            table: records_frame(shown, with_project),
            download: gr.update(value=str(path) if path else None, interactive=bool(path)),
        }

    async def load(
        active_id: str | None, chosen_scope: str, simulated: bool, role: str, status: str
    ) -> dict:
        project_id = active_id if chosen_scope == ACTIVE else None
        if chosen_scope == ACTIVE and not active_id:
            return empty(NO_PROJECT)
        try:
            summary = await client.costs(project_id, simulated, MAX_RECORDS)
            prices = await client.pricing()
        except ApiError as exc:
            gr.Warning(exc.detail)
            return empty(f"### Costes no disponibles\n{exc.detail}")
        name = summary.get("project_name")
        title = (
            "todos los proyectos" if project_id is None else f"«{name}»" if name else "el proyecto"
        )
        records = summary["records"]
        roles, projects = role_frame(summary), project_frame(summary)
        return {
            heading: f"### Costes de IA de {title}",
            kpis: kpi_html(summary),
            notes: " ".join(
                [*alert_lines(await client.cost_alerts(), project_id), notes_md(summary)]
            ),
            by_role: gr.update(value=roles, y_lim=y_range(roles)),
            by_day: day_role_frame(records),
            by_project: gr.update(
                value=projects, y_lim=y_range(projects), visible=project_id is None
            ),
            records_state: records,
            all_projects: project_id is None,
            pricing: pricing_frame(prices),
            **table_updates(records, role, status, project_id is None),
        }

    inputs = [active, scope, include_simulated, role_filter, status_filter]
    for trigger in (scope.change, include_simulated.change, refresh.click):
        trigger(load, inputs=inputs, outputs=outputs)

    def on_filter(
        records: list[dict[str, Any]], role: str, status: str, with_project: bool
    ) -> dict:
        return table_updates(records, role, status, with_project)

    for dropdown in (role_filter, status_filter):
        dropdown.change(
            on_filter,
            inputs=[records_state, role_filter, status_filter, all_projects],
            outputs=[table, download],
        )

    async def refresh_all(active_id: str | None) -> dict:
        return await load(active_id, ACTIVE, False, ALL, ALL)

    return CostsTab(refresh_all, outputs, load, inputs)
