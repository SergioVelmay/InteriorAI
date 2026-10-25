"""Retoque de zona: solo composiciones, con máscara nativa y la imagen completa (B-038)."""

import io

import httpx
from conftest import UI, Projects
from PIL import Image
from playwright.sync_api import expect


def prepared(api: httpx.Client, projects: Projects) -> tuple[dict, dict]:
    """Proyecto con boceto y composición seleccionados (por API, en mock)."""
    project = projects.create("retoque")
    url = project["url"]
    draft = api.post(f"{url}/renders/drafts", json={"n": 1}).json()["renders"][0]
    api.post(f"{url}/renders/{draft['id']}/select")
    composition = api.post(f"{url}/renders/compositions", json={"draft_id": draft["id"]})
    composition = composition.json()["renders"][0]
    api.post(f"{url}/renders/{composition['id']}/select")
    return project, composition


def image(api: httpx.Client, url: str, render_id: str) -> Image.Image:
    content = api.get(f"{url}/assets/{render_id}/content").content
    return Image.open(io.BytesIO(content)).convert("RGB")


def test_inpaint_composition(ui: UI, projects: Projects, api: httpx.Client) -> None:
    page = ui.page
    project, composition = prepared(api, projects)
    url = project["url"]
    ui.activate(project["name"])
    ui.tab("Estudio")
    page.get_by_role("tab", name="Composición").click()
    page.get_by_text("Retocar zona de la composición").click()
    expect(page.locator("#iai-inpaint-editor canvas").first).to_be_visible()
    page.wait_for_timeout(2500)  # editor nuevo con la composición (gr.render)
    page.locator("#iai-inpaint").click()
    ui.toast("Pinta en la imagen la zona")  # sin trazos no hay llamada

    ui.paint()
    page.locator("#iai-inpaint-instruction textarea").fill("Una planta en la esquina")
    page.locator("#iai-inpaint").click()
    ui.toast("Retoque generado", timeout=60_000)
    retouched = page.locator("#iai-compositions .thumbnail-item", has_text="retoque")
    expect(retouched).to_have_count(1)
    stage = api.get(f"{url}/renders", params={"stage": "composicion"}).json()
    retouch = next(r for r in stage if r.get("inpaint"))
    assert retouch["inpaint"]["method"] == "mascara"
    assert 0 < retouch["inpaint"]["coverage"] < 0.2
    original, edited = image(api, url, composition["id"]), image(api, url, retouch["id"])
    assert edited.size == original.size and edited.tobytes() != original.tobytes()
