"""Aplicación Gradio de InteriorAI.

python -m ui
"""

from __future__ import annotations

from typing import Any

import gradio as gr

from shared import Settings, get_settings
from ui.api_client import BackendClient
from ui.tabs.assets import build_assets_tab
from ui.tabs.costs import build_costs_tab
from ui.tabs.projects import build_projects_tab
from ui.tabs.studio import build_studio_tab
from ui.theme import CSS, FORCE_DARK_JS, build_theme
from ui.views import header_html

ACTIVE_PROJECT_KEY = "interiorai.active_project"


def build_app(settings: Settings, client: BackendClient | None = None) -> gr.Blocks:
    client = client or BackendClient(settings.network.backend_url)
    data_dir = settings.storage.data_dir

    with gr.Blocks(title="InteriorAI", analytics_enabled=False) as demo:
        active = gr.BrowserState(None, storage_key=ACTIVE_PROJECT_KEY)
        header = gr.HTML(header_html(None, None))
        with gr.Tabs():
            with gr.Tab("Proyectos"):
                projects = build_projects_tab(client, data_dir, active, header)
            with gr.Tab("Assets") as assets_tab:
                assets = build_assets_tab(client, data_dir, active)
            with gr.Tab("Estudio") as studio_tab:
                studio = build_studio_tab(client, data_dir, active)
            with gr.Tab("Costes IA") as costs_tab:
                costs = build_costs_tab(client, active)

        demo.load(projects.refresh_all, inputs=active, outputs=projects.all_outputs)
        # Al entrar en Assets se recarga con el proyecto activo (puede haber cambiado).
        assets_tab.select(assets.refresh_all, inputs=active, outputs=assets.all_outputs)
        studio_tab.select(studio.refresh_all, inputs=active, outputs=studio.all_outputs)
        costs_tab.select(costs.load, inputs=costs.inputs, outputs=costs.all_outputs)
    return demo


def launch_kwargs(settings: Settings) -> dict[str, Any]:
    return {
        "server_name": "0.0.0.0",  # noqa: S104 — dentro del contenedor; compose publica en 127.0.0.1
        "server_port": settings.network.frontend_port,
        "theme": build_theme(),
        "css": CSS,
        "js": FORCE_DARK_JS,
        # Las portadas se leen del volumen compartido (montado en solo lectura).
        "allowed_paths": [str(settings.storage.data_dir)],
        "footer_links": [],  # sin el pie de Gradio («Use via API», «Built with Gradio»)
    }


def main() -> None:
    settings = get_settings()
    build_app(settings).launch(**launch_kwargs(settings))
