"""Pestaña Estudio: ciclo HITL completo (brief → bocetos → composición → final → auditoría)."""

import httpx
from conftest import UI, Projects
from playwright.sync_api import expect

EDITED = "Olive wide-wale corduroy modular sofa, watercolor"


def test_studio_hitl_cycle(ui: UI, projects: Projects, api: httpx.Client) -> None:
    page = ui.page
    project = projects.create("estudio")
    ui.activate(project["name"])
    ui.tab("Estudio")
    expect(page.get_by_text(f"Estudio de «{project['name']}»")).to_be_visible()

    page.locator("#iai-gen-brief").click()
    ui.toast("Brief v1 generado")
    # El aviso llega antes de que la vista se actualice: se espera al brief nuevo.
    expect(page.locator("#iai-brief-version input")).to_have_value("v1 · propuesto")
    page.get_by_text("Prompts de imagen").click()
    prompt = page.locator("#iai-prompt-fast textarea")
    expect(prompt).to_have_value("mock")
    prompt.fill(EDITED)
    page.locator("#iai-save-prompts").click()
    ui.toast("Prompts guardados")
    saved = api.get(f"{project['url']}/briefs").json()[0]["content"]["image_prompts"]
    assert saved["fast_draft"] == EDITED
    page.locator("#iai-approve-brief").click()
    ui.toast("Brief aprobado")

    page.locator("#iai-gen-drafts").click()
    ui.toast("Boceto: 2 imagen(es)")
    expect(page.locator("#iai-drafts .thumbnail-item")).to_have_count(2)
    page.locator("#iai-drafts .thumbnail-item").first.click()
    page.locator("#iai-select").click()
    ui.toast("Imagen seleccionada")
    drafts = api.get(f"{project['url']}/renders", params={"stage": "boceto"}).json()
    assert all(d["prompt"].startswith(EDITED) for d in drafts)

    page.locator("#iai-gen-composition").click()
    ui.toast("Composición: 1 imagen(es)")
    page.locator("#iai-compositions .thumbnail-item").first.click()
    page.locator("#iai-select").click()
    selected = page.locator("#iai-compositions .thumbnail-item", has_text="seleccionado")
    expect(selected).to_have_count(1)

    page.locator("#iai-gen-final").click()
    ui.toast("Render final: 1 imagen(es)")
    expect(page.locator("#iai-finals .thumbnail-item")).to_have_count(1)
    final = api.get(f"{project['url']}/renders", params={"stage": "render_final"}).json()[0]
    assert final["size"] == "1920x1080"  # proporción de la captura (16:9)

    page.locator("#iai-audit").click()
    ui.toast("Auditoría: ")
    expect(page.locator("#iai-finals .thumbnail-item", has_text="auditoría")).to_have_count(1)

    page.locator("#iai-render-feedback textarea").fill("Más luz natural")
    page.locator("#iai-reject-render").click()
    ui.toast("Imagen rechazada y regenerada")
    expect(page.locator("#iai-finals .thumbnail-item")).to_have_count(2)
    expect(page.locator("#iai-finals .thumbnail-item", has_text="rechazado")).to_have_count(1)
    page.locator("#iai-select").click()
    expect(page.locator("#iai-finals .thumbnail-item", has_text="seleccionado")).to_have_count(1)
    expect(page.get_by_text("Coste acumulado de la cadena").first).to_be_visible()

    expect(page.get_by_text("Confirmar (con coste)")).to_be_hidden()  # en mock no se confirma
