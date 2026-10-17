import gradio as gr
import httpx
import pytest

from shared import Settings
from ui.app import badge, build_app, fetch_backend_status, launch_kwargs

BACKEND = "http://backend.test"


def transport_returning(status_code: int, payload: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(handler)


async def test_status_ok_shows_connected_and_mode() -> None:
    transport = transport_returning(200, {"status": "ok", "mode": "mock"})
    result = await fetch_backend_status(BACKEND, transport)
    assert "iai-ok" in result
    assert "Backend conectado · modo mock" in result


async def test_status_degraded() -> None:
    transport = transport_returning(503, {"status": "degraded", "mode": "mock"})
    result = await fetch_backend_status(BACKEND, transport)
    assert "iai-warn" in result
    assert "degradado" in result


async def test_status_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión", request=request)

    result = await fetch_backend_status(BACKEND, httpx.MockTransport(handler))
    assert "iai-error" in result
    assert "no disponible" in result


def test_badge_escapes_html() -> None:
    assert "<script>" not in badge("ok", "<script>alert(1)</script>")


@pytest.fixture
def settings() -> Settings:
    return Settings.load(env_file=None)


def test_build_app_returns_blocks(settings: Settings) -> None:
    assert isinstance(build_app(settings), gr.Blocks)


def test_launch_kwargs_force_dark_theme(settings: Settings) -> None:
    kwargs = launch_kwargs(settings)
    assert "dark" in kwargs["js"]
    assert isinstance(kwargs["theme"], gr.themes.Base)
    assert kwargs["server_port"] == settings.network.frontend_port
