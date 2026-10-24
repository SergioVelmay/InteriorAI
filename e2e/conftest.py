"""Pruebas de extremo a extremo con Playwright contra la app levantada en modo mock.

    docker compose up -d --build --wait
    uv run --group e2e playwright install chromium            # una vez (o usa Edge)
    uv run --group e2e pytest e2e --browser-channel msedge    # en local, con el Edge instalado
    uv run --group e2e pytest e2e                             # en la CI, con Chromium

Cada prueba crea sus propios proyectos «E2E …» y los mueve a la papelera al terminar. Se
niegan a ejecutarse si el backend no está en modo mock: nunca generan coste.
"""

from __future__ import annotations

import io
import os
from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest
from PIL import Image
from playwright.sync_api import Page, expect

FRONTEND_URL = os.environ.get("E2E_FRONTEND_URL", "http://127.0.0.1:7860/")
BACKEND_URL = os.environ.get("E2E_BACKEND_URL", "http://127.0.0.1:8000")
TIMEOUT_MS = 30_000
expect.set_options(timeout=TIMEOUT_MS)  # Gradio tarda en actualizar tras cada evento


def png(size: tuple[int, int], color: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture(scope="session")
def api() -> Iterator[httpx.Client]:
    try:
        health = httpx.get(f"{BACKEND_URL}/health", timeout=10).json()
    except httpx.HTTPError as exc:
        pytest.fail(f"Backend no disponible en {BACKEND_URL} (¿docker compose up?): {exc}")
    if health["mode"] != "mock":
        pytest.exit("Las pruebas E2E solo se ejecutan con AI_PROVIDER_MODE=mock", returncode=2)
    with httpx.Client(base_url=f"{BACKEND_URL}/api/v1", timeout=120) as client:
        yield client


class Projects:
    """Proyectos de prueba con nombre único; se mueven a la papelera al terminar."""

    def __init__(self, api: httpx.Client) -> None:
        self.api = api
        self.names: list[str] = []

    def name(self, label: str) -> str:
        name = f"E2E {label} {uuid4().hex[:6]}"
        self.names.append(name)
        return name

    def create(self, label: str, capture: bool = True, reference: bool = True) -> dict:
        project = self.api.post(
            "/projects", json={"name": self.name(label),
                               "description": "Sofá en L, tonos verdes"},
        ).json()  # fmt: skip
        url = f"/projects/{project['id']}"
        if capture:
            self.upload(url, "referencia", "vista.png", png((1600, 900), "#b45309"))
        if reference:
            self.upload(url, "referencia", "sofa.png", png((900, 500), "#556b2f"))
        return project | {"url": url}

    def upload(self, url: str, kind: str, name: str, content: bytes) -> str:
        response = self.api.post(f"{url}/assets/{kind}", files={"file": (name, content)})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def cleanup(self) -> None:
        for project in self.api.get("/projects").json():
            if project["name"] in self.names:
                self.api.delete(f"/projects/{project['id']}")


@pytest.fixture
def projects(api: httpx.Client) -> Iterator[Projects]:
    factory = Projects(api)
    yield factory
    factory.cleanup()


@pytest.fixture
def browser_context_args(browser_context_args: dict) -> dict:
    return {**browser_context_args, "viewport": {"width": 1600, "height": 1300},
            "accept_downloads": True}  # fmt: skip


class UI:
    """Acciones comunes sobre la interfaz Gradio."""

    def __init__(self, page: Page) -> None:
        self.page = page
        page.set_default_timeout(TIMEOUT_MS)

    def open(self) -> None:
        # Gradio mantiene una conexión abierta: se espera a la carga y a un texto visible.
        self.page.goto(FRONTEND_URL, wait_until="load")
        self.page.wait_for_selector("text=Backend conectado")

    def activate(self, name: str) -> None:
        self.open()  # recarga: el proyecto pudo crearse (por API) después de abrir la página
        self.page.locator(".iai-gallery .thumbnail-item", has_text=name).first.click()
        expect(self.page.get_by_text(f"Proyecto: {name}")).to_be_visible()

    def tab(self, title: str) -> None:
        self.page.get_by_role("tab", name=title).click()

    def toast(self, text: str, timeout: int = TIMEOUT_MS) -> None:
        expect(self.page.get_by_text(text).first).to_be_visible(timeout=timeout)

    def paint(self, selector: str = "#iai-inpaint-editor canvas") -> None:
        """Un trazo en el centro del lienzo (antes, a la vista: fuera de ella se pierde)."""
        canvas = self.page.locator(selector).first
        expect(canvas).to_be_visible()
        canvas.scroll_into_view_if_needed()
        self.page.wait_for_timeout(500)
        box = canvas.bounding_box()
        assert box is not None
        x, y = box["x"] + box["width"] * 0.45, box["y"] + box["height"] * 0.45
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        for step in range(12):
            self.page.mouse.move(x + step * box["width"] * 0.01, y + (step % 3) * 8, steps=3)
        self.page.mouse.up()


@pytest.fixture
def ui(page: Page, api: httpx.Client) -> UI:
    interface = UI(page)
    interface.open()
    return interface
