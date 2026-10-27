"""Retoque de la composición seleccionada (Paso 23): máscara nativa, prompt del PROMPT_ARCHITECT y
la imagen completa del modelo (B-038), al generar con la composición actual y «Usar el retoque»."""

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
    ui.tab("Composición")
    # ② plegada (B-074): el editor se monta al desplegarla.
    ui.expand("iai-retouch-section")
    expect(page.locator("#iai-inpaint-editor canvas").first).to_be_visible()
    page.wait_for_timeout(2500)  # editor nuevo con la composición (gr.render)
    # B-039: pincel rojo fijo, sin paleta de colores; etiquetas en español (B-071).
    editor = page.locator("#iai-inpaint-editor")
    expect(editor.get_by_role("button", name="Color")).to_be_hidden()
    size = editor.get_by_role("button", name="Tamaño del pincel")
    expect(size).to_be_visible()  # icono de tamaño: circunferencias (CSS), no la señal de prohibido
    expect(size.locator("svg")).to_be_hidden()
    # B-072: la rueda sobre el lienzo desplaza la página, sin zoom.
    editor.locator("canvas").first.hover()
    before = page.evaluate("window.scrollY")
    page.mouse.wheel(0, 300)
    page.wait_for_function(f"window.scrollY > {before}")
    # B-073: aviso de que las indicaciones solo actúan en la zona pintada.
    expect(page.locator("#iai-retouch-hint")).to_be_hidden()
    page.locator("#iai-use-retouch input").check()
    expect(page.locator("#iai-retouch-hint")).to_contain_text("solo actúan dentro de la zona")
    page.locator("#iai-gen-compositions-current").click()
    ui.toast("Pinta en la imagen la zona")  # sin trazos no hay llamada

    ui.paint()
    page.locator("#iai-gen-compositions-current").click()
    ui.toast("Describe el cambio")
    page.locator("#iai-inpaint-instruction textarea").fill("Una planta en la esquina")
    page.locator("#iai-gen-compositions-current").click()
    ui.toast("Retoque generado", timeout=60_000)
    retouched = page.locator("#iai-compositions .thumbnail-item", has_text="retoque")
    expect(retouched).to_have_count(1)
    stage = api.get(f"{url}/renders", params={"stage": "composicion"}).json()
    retouch = next(r for r in stage if r.get("inpaint"))
    assert "method" not in retouch["inpaint"]  # solo con máscara nativa (Paso 33)
    assert retouch["inpaint"]["instruction"] == "Una planta en la esquina"
    assert 0 < retouch["inpaint"]["coverage"] < 0.2
    assert retouch["prompt_info"] is not None  # el prompt lo escribe el PROMPT_ARCHITECT
    original, edited = image(api, url, composition["id"]), image(api, url, retouch["id"])
    assert edited.size == original.size and edited.tobytes() != original.tobytes()
