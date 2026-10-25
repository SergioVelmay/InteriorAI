from pathlib import Path
from uuid import uuid4

import gradio as gr
import httpx
import pytest

from shared import Settings
from shared.models import utc_now
from ui.api_client import BackendClient
from ui.app import build_app, launch_kwargs
from ui.tabs.projects import build_projects_tab


def fake_backend(projects: list[dict], mode: str = "mock") -> BackendClient:
    by_id = {p["id"]: p for p in projects}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/health":
            return httpx.Response(
                200,
                json={"status": "ok", "version": "0.1.0", "mode": mode, "data_dir_writable": True},
            )
        if path == "/api/v1/projects":
            return httpx.Response(200, json=[
                {k: p[k] for k in ("id", "name", "created_at", "updated_at")}
                for p in projects
            ])  # fmt: skip
        if path.endswith("/costs"):
            return httpx.Response(200, json={"totals": {"cost_eur": 0.1, "calls": 2}})
        project_id = path.rsplit("/", 1)[1]
        if project_id in by_id:
            return httpx.Response(200, json=by_id[project_id])
        return httpx.Response(404, json={"detail": "Proyecto no encontrado"})

    return BackendClient("http://backend.test", transport=httpx.MockTransport(handler))


def project_json(name: str) -> dict:
    now = utc_now().isoformat()
    return {
        "schema_version": 2, "id": str(uuid4()), "name": name,
        "description": "", "created_at": now, "updated_at": now, "assets": [], "briefs": [],
        "renders": [],
    }  # fmt: skip


@pytest.fixture
def settings() -> Settings:
    return Settings.load(env_file=None)


def build_tab(client: BackendClient, data_dir: Path):
    with gr.Blocks():
        active = gr.BrowserState(None)
        header = gr.HTML()
        tab = build_projects_tab(client, data_dir, active, header)
    return tab, active, header


def test_build_app_returns_blocks(settings: Settings) -> None:
    assert isinstance(build_app(settings, fake_backend([])), gr.Blocks)


def test_launch_kwargs(settings: Settings) -> None:
    kwargs = launch_kwargs(settings)
    assert "dark" in kwargs["js"]
    assert isinstance(kwargs["theme"], gr.themes.Base)
    assert kwargs["server_port"] == settings.network.frontend_port
    assert kwargs["allowed_paths"] == [str(settings.storage.data_dir)]


async def test_refresh_loads_gallery_and_active_project(tmp_path: Path) -> None:
    first, second = project_json("Dormitorio"), project_json("Estudio")
    tab, active, header = build_tab(fake_backend([first, second], mode="azure"), tmp_path)

    result = await tab.refresh_all(second["id"])
    assert result[active] == second["id"]
    assert "Proyecto: Estudio" in result[header]
    assert "Azure · con coste" in result[header]
    gallery = result[tab.gallery]
    assert len(gallery["value"]) == 2
    assert gallery["selected_index"] == 1
    assert gallery["value"][0][1].startswith("Dormitorio · ")
    assert gallery["value"][1][1].startswith("Estudio · ")
    assert "**0.1000 €** en 2 llamadas" in result[tab.summary]
    assert result[tab.fields[0]] == "Estudio"


async def test_refresh_falls_back_to_the_latest_project(tmp_path: Path) -> None:
    """B-025: si el proyecto recordado no existe (o no hay ninguno), el último actualizado."""
    latest = project_json("Dormitorio")
    tab, active, header = build_tab(fake_backend([latest, project_json("Estudio")]), tmp_path)
    for remembered in (str(uuid4()), None):  # ya no existe / otro navegador
        result = await tab.refresh_all(remembered)
        assert result[active] == latest["id"]
        assert "Proyecto: Dormitorio" in result[header]
        assert result[tab.gallery]["selected_index"] == 0

    empty, active, header = build_tab(fake_backend([]), tmp_path)
    result = await empty.refresh_all(None)
    assert result[active] is None
    assert "Sin proyecto activo" in result[header]
    assert "Ningún proyecto seleccionado" in result[empty.summary]


def test_handlers_never_return_an_empty_dict() -> None:
    """Regresión (Paso 12): Gradio trata `{}` como un único valor y el evento falla."""
    for module in Path(__file__).resolve().parents[1].joinpath("ui", "tabs").glob("*.py"):
        assert "return {}" not in module.read_text(encoding="utf-8"), module.name
