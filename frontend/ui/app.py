"""Aplicación Gradio de InteriorAI.

python -m ui
"""

from __future__ import annotations

import html
from typing import Any, Literal

import gradio as gr
import httpx

from shared import Settings, get_settings
from ui.theme import CSS, FORCE_DARK_JS, build_theme

BadgeLevel = Literal["ok", "warn", "error", "pending"]

HEADER_HTML = """
<div class="iai-header">
  <h1>InteriorAI</h1>
  <p>Estudio de interiorismo asistido por IA · supervisión humana en cada etapa</p>
</div>
"""


def badge(level: BadgeLevel, text: str) -> str:
    return (
        f'<span class="iai-badge iai-{level}"><span class="iai-dot"></span>'
        f"{html.escape(text)}</span>"
    )


async def fetch_backend_status(
    base_url: str, transport: httpx.AsyncBaseTransport | None = None
) -> str:
    """Consulta `/health` del backend y devuelve un badge HTML."""
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=5, transport=transport) as client:
            response = await client.get("/health")
        body = response.json()
    except (httpx.HTTPError, ValueError):
        return badge("error", "Backend no disponible")
    mode = body.get("mode", "?")
    if response.status_code == 200 and body.get("status") == "ok":
        return badge("ok", f"Backend conectado · modo {mode}")
    return badge("warn", f"Backend degradado · almacenamiento no disponible · modo {mode}")


def build_app(settings: Settings) -> gr.Blocks:
    backend_url = settings.network.backend_url

    async def check_backend() -> str:
        return await fetch_backend_status(backend_url)

    with gr.Blocks(title="InteriorAI", analytics_enabled=False) as demo:
        gr.HTML(HEADER_HTML)
        with gr.Row(equal_height=True):
            status = gr.HTML(badge("pending", "Comprobando backend…"))
            refresh = gr.Button("Comprobar conexión", variant="secondary", size="sm", scale=0)
        gr.Markdown(
            "Esqueleto de la interfaz. Las pestañas de **Proyectos**, **Assets**, "
            "**Estudio** y **Costes** se añadirán en los Pasos 11 a 14."
        )
        demo.load(check_backend, outputs=status)
        refresh.click(check_backend, outputs=status)
    return demo


def launch_kwargs(settings: Settings) -> dict[str, Any]:
    return {
        "server_name": "0.0.0.0",  # noqa: S104 — dentro del contenedor; compose publica en 127.0.0.1
        "server_port": settings.network.frontend_port,
        "theme": build_theme(),
        "css": CSS,
        "js": FORCE_DARK_JS,
    }


def main() -> None:
    settings = get_settings()
    build_app(settings).launch(**launch_kwargs(settings))
