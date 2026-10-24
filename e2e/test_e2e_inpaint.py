"""Retoque de zona: solo composiciones, con máscara nativa y la imagen completa (B-038)."""

import io

import httpx
from conftest import UI, Projects
from PIL import Image
from playwright.sync_api import expect


def prepared(api: httpx.Client, projects: Projects) -> tuple[dict, dict, dict]:
    """Proyecto con composición y render final seleccionados (por API, en mock)."""
    project = projects.create("retoque")
    url = project["url"]
    brief = api.post(f"{url}/briefs").json()["brief"]
    api.post(f"{url}/briefs/{brief['id']}/approve")
    composition = api.post(f"{url}/renders/compositions", json={}).json()["renders"][0]
    api.post(f"{url}/renders/{composition['id']}/select")
    final = api.post(f"{url}/renders/final", json={"composition_id": composition["id"]})
    final = final.json()["renders"][0]
    api.post(f"{url}/renders/{final['id']}/select")
    return project, composition, final


def image(api: httpx.Client, url: str, render_id: str) -> Image.Image:
    content = api.get(f"{url}/assets/{render_id}/content").content
    return Image.open(io.BytesIO(content)).convert("RGB")


def test_inpaint_composition(ui: UI, projects: Projects, api: httpx.Client) -> None:
    page = ui.page
    project, composition, _ = prepared(api, projects)
    url = project["url"]
    ui.activate(project["name"])
    ui.tab("Estudio")
    expect(page.get_by_text(f"Estudio de «{project['name']}»")).to_be_visible()

    # El visor abre el render final seleccionado: no se puede retocar.
    page.get_by_text("Retocar zona (composición)").click()
    expect(page.get_by_text("Elige una composición en el visor.")).to_be_visible()

    page.locator("#iai-compositions .thumbnail-item").first.click()
    expect(page.get_by_text(f"Composición {composition['id'][:8]}").first).to_be_visible()
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
    expect(page.locator("#iai-inpaint-files .thumbnail-item")).to_have_count(1)  # la máscara
