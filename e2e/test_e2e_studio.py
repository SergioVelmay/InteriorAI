"""Bocetos → Composición → Render Final (Pasos 22-23): pestañas de primer nivel con desbloqueo
progresivo, prompt automático, auditoría del boceto y selección única por etapa."""

import httpx
from conftest import UI, Projects
from playwright.sync_api import expect


def test_studio_three_tabs(ui: UI, projects: Projects, api: httpx.Client) -> None:
    page = ui.page
    project = projects.create("estudio")  # vista + sofá, analizadas (activas en mock)
    ui.activate(project["name"])
    expect(page.get_by_role("tab", name="Estudio")).to_have_count(0)  # sin pestaña Estudio
    # Composición y Render Final, bloqueadas hasta seleccionar en la etapa anterior (B-043).
    expect(page.get_by_role("tab", name="Composición")).to_be_disabled()
    expect(page.get_by_role("tab", name="Render Final")).to_be_disabled()
    ui.tab("Bocetos")
    expect(page.get_by_text("Referencias activas (2)")).to_be_visible()
    expect(page.locator("#iai-studio-references .iai-thumb")).to_have_count(2)
    expect(page.locator("#iai-studio-references .iai-thumb.start")).to_have_count(1)  # la base

    # ① Bocetos: sin brief; el prompt se escribe al generar.
    page.locator("#iai-draft-indications textarea").fill("Más cálido")
    page.locator("#iai-gen-drafts").click()
    ui.toast("Boceto: 4 imagen(es)")
    expect(page.locator("#iai-drafts .thumbnail-item")).to_have_count(4)
    drafts = api.get(f"{project['url']}/renders", params={"stage": "boceto"}).json()
    assert all(d["prompt_info"] and d["brief_id"] is None for d in drafts)
    expect(page.locator("#iai-more-drafts")).to_contain_text("Lo que ha entendido la IA")
    page.locator("#iai-drafts .thumbnail-item").nth(1).click()
    page.locator("#iai-select-drafts").click()
    ui.toast("Imagen seleccionada (boceto)")
    expect(page.locator("#iai-select-drafts")).to_contain_text("Seleccionada")

    # ② Composición: auditoría del boceto (B-046) y composición con ella.
    composition_tab = page.get_by_role("tab", name="Composición")
    expect(composition_tab).to_be_enabled()
    composition_tab.click()
    # ① y ② plegadas (B-074): sin auditoría todavía, ① empieza cerrada.
    expect(page.locator("#iai-audit-notes textarea")).to_be_hidden()
    ui.expand("iai-audit-section")
    # En mock la ficha lo marca todo: las dos referencias aportan geometría, más el boceto.
    expect(page.locator("#iai-audit-images .iai-thumb")).to_have_count(3)
    expect(page.locator("#iai-gen-compositions-current")).to_be_disabled()  # sin composición
    page.locator("#iai-audit-notes textarea").fill("Falta la lámpara de pie")
    page.locator("#iai-gen-audit").click()
    ui.toast("Auditoría: ")
    expect(page.locator("#iai-audit-report")).to_contain_text("/100")
    page.locator("#iai-use-audit input").check()
    page.locator("#iai-gen-compositions").click()
    ui.toast("Composición: 1 imagen(es)")
    [composition] = api.get(f"{project['url']}/renders", params={"stage": "composicion"}).json()
    chosen = next(d for d in api.get(f"{project['url']}/renders").json()
                  if d["stage"] == "boceto" and d["status"] == "seleccionado")  # fmt: skip
    assert composition["parent_render_id"] == chosen["id"]  # parte del boceto seleccionado
    assert composition["input_asset_ids"][0] == chosen["id"]
    page.locator("#iai-select-compositions").click()
    ui.toast("Imagen seleccionada (composición)")
    expect(page.locator("#iai-more-compositions")).to_contain_text("Lo que ha entendido la IA")

    # Con la composición actual (B-055).
    expect(page.locator("#iai-gen-compositions-current")).to_be_enabled()
    page.locator("#iai-gen-compositions-current").click()
    expect(page.locator("#iai-compositions .thumbnail-item")).to_have_count(2)
    compositions = api.get(f"{project['url']}/renders", params={"stage": "composicion"}).json()
    assert compositions[0]["parent_render_id"] == composition["id"]

    # ③ Render Final (Paso 24): solo la imagen de partida y el prompt, 3:2 a 4 MP por defecto.
    final_tab = page.get_by_role("tab", name="Render Final")
    expect(final_tab).to_be_enabled()
    final_tab.click()
    expect(page.locator("#iai-audit-final")).to_have_count(0)
    expect(page.locator("#iai-gen-finals-current")).to_be_disabled()  # sin render final
    page.locator("#iai-final-indications textarea").fill("De noche")
    page.locator("#iai-gen-finals").click()
    ui.toast("Render final: 1 imagen(es)")
    [final] = api.get(f"{project['url']}/renders", params={"stage": "render_final"}).json()
    assert final["size"] == "2448x1632" and len(final["input_asset_ids"]) == 1

    # Proporción 16:9: la resolución pasa a la máxima de esa proporción.
    page.locator("#iai-final-ratio").get_by_text("16:9").click()
    expect(page.locator("#iai-final-size")).to_contain_text("2560 x 1440")
    page.locator("#iai-select-finals").click()
    ui.toast("Imagen seleccionada (render final)")
    expect(page.locator("#iai-gen-finals-current")).to_be_enabled()
    page.locator("#iai-gen-finals-current").click()
    expect(page.locator("#iai-finals .thumbnail-item")).to_have_count(2)
    finals = api.get(f"{project['url']}/renders", params={"stage": "render_final"}).json()
    assert finals[0]["parent_render_id"] == final["id"] and finals[0]["size"] == "2560x1440"

    # «Otra versión» de la imagen mostrada: mismo prompt, partida y tamaño (B-051).
    page.locator("#iai-gen-finals-variant").click()
    expect(page.locator("#iai-finals .thumbnail-item")).to_have_count(3)
    variant = api.get(f"{project['url']}/renders", params={"stage": "render_final"}).json()[0]
    assert variant["variant_of_id"] == finals[0]["id"] and variant["prompt"] == finals[0]["prompt"]

    # Una sola imagen seleccionada por etapa (B-043).
    page.locator("#iai-select-finals").click()
    selected = page.locator("#iai-finals .thumbnail-item", has_text="seleccionado")
    expect(selected).to_have_count(1)
    expect(page.get_by_text("Confirmar (con coste)")).to_be_hidden()  # en mock no se confirma
