"""Pestaña Estudio (Paso 22): Bocetos → Composición → Render Final, con desbloqueo progresivo,
prompt automático, «Ver más» y selección única por etapa."""

import httpx
from conftest import UI, Projects
from playwright.sync_api import expect


def test_studio_three_tabs(ui: UI, projects: Projects, api: httpx.Client) -> None:
    page = ui.page
    project = projects.create("estudio")  # vista + sofá, analizadas (activas en mock)
    ui.activate(project["name"])
    ui.tab("Estudio")
    expect(page.get_by_text("Referencias activas (2)")).to_be_visible()
    # Composición y Render Final, bloqueadas hasta seleccionar en la etapa anterior (B-043).
    expect(page.get_by_role("tab", name="Composición")).to_be_disabled()
    expect(page.get_by_role("tab", name="Render Final")).to_be_disabled()

    # ① Bocetos: sin brief; el prompt se escribe al generar.
    page.locator("#iai-draft-indications textarea").fill("Más cálido")
    page.locator("#iai-gen-drafts").click()
    ui.toast("Boceto: 4 imagen(es)")
    expect(page.locator("#iai-drafts .thumbnail-item")).to_have_count(4)
    drafts = api.get(f"{project['url']}/renders", params={"stage": "boceto"}).json()
    assert all(d["prompt_info"] and d["brief_id"] is None for d in drafts)
    page.get_by_text("Ver más: lo que entendió la IA").first.click()
    expect(page.locator("#iai-more-drafts")).to_contain_text("Lo que ha entendido la IA")
    page.locator("#iai-drafts .thumbnail-item").nth(1).click()
    page.locator("#iai-select-drafts").click()
    ui.toast("Imagen seleccionada (boceto)")
    expect(page.locator("#iai-select-drafts")).to_contain_text("Seleccionada")

    # ② Composición (provisional hasta el Paso 23).
    composition_tab = page.get_by_role("tab", name="Composición")
    expect(composition_tab).to_be_enabled()
    composition_tab.click()
    page.locator("#iai-gen-compositions").click()
    ui.toast("Composición: 1 imagen(es)")
    page.locator("#iai-select-compositions").click()
    ui.toast("Imagen seleccionada (composición)")

    # ③ Render Final (provisional hasta el Paso 24).
    final_tab = page.get_by_role("tab", name="Render Final")
    expect(final_tab).to_be_enabled()
    final_tab.click()
    page.locator("#iai-gen-finals").click()
    ui.toast("Render final: 1 imagen(es)")
    final = api.get(f"{project['url']}/renders", params={"stage": "render_final"}).json()[0]
    assert final["size"] == "1920x1080"  # proporción de la imagen base (16:9)
    page.locator("#iai-audit-final").click()
    ui.toast("Auditoría: ")
    expect(page.locator("#iai-finals .thumbnail-item", has_text="auditoría")).to_have_count(1)

    # Una sola imagen seleccionada por etapa (B-043).
    page.locator("#iai-select-finals").click()
    page.locator("#iai-gen-finals").click()
    ui.toast("Render final: 1 imagen(es)")
    page.locator("#iai-select-finals").click()  # la nueva, que es la que se muestra
    selected = page.locator("#iai-finals .thumbnail-item", has_text="seleccionado")
    expect(selected).to_have_count(1)
    expect(page.get_by_text("Confirmar (con coste)")).to_be_hidden()  # en mock no se confirma
