"""Cuadros de texto (B-115): se vacían al enviarse con éxito (lo escrito queda con la imagen o
con la auditoría) y al cambiar de proyecto, para no enviar por error lo que era para otra."""

from conftest import UI, Projects
from playwright.sync_api import expect


def test_texts_are_cleared_when_sent_or_on_another_project(ui: UI, projects: Projects) -> None:
    page = ui.page
    first, second = projects.create("textos A"), projects.create("textos B")
    ui.activate(first["name"])
    ui.tab("Bocetos")
    indications = page.locator("#iai-draft-indications textarea")

    # Al generar, el cuadro se vacía y lo escrito se ve con la imagen.
    indications.fill("Más luz de tarde")
    page.locator("#iai-gen-drafts").click()
    ui.toast("Boceto: 4 imagen(es)")
    expect(indications).to_have_value("")
    expect(page.locator("#iai-more-drafts")).to_contain_text("Tus indicaciones: «Más luz de tarde»")

    # Las observaciones de la auditoría: se vacían al auditar y quedan con la auditoría.
    page.locator("#iai-drafts .thumbnail-item").nth(0).click()
    page.locator("#iai-select-drafts").click()
    ui.toast("Imagen seleccionada (boceto)")
    ui.tab("Composición")
    ui.expand("iai-audit-section")
    notes = page.locator("#iai-audit-notes textarea")
    notes.fill("Falta la lámpara de pie")
    page.locator("#iai-gen-audit").click()
    ui.toast("Auditoría: ")
    expect(notes).to_have_value("")
    expect(page.locator("#iai-audit-report")).to_contain_text(
        "Tus observaciones: «Falta la lámpara"
    )

    # Lo escrito sin enviar no pasa a otro proyecto.
    page.locator("#iai-composition-indications textarea").fill("Era para el proyecto A")
    page.locator("#iai-use-audit input").check()
    ui.tab("Bocetos")
    indications.fill("También era para A")

    def switch(project: dict) -> None:  # desde la galería, sin recargar la página
        ui.tab("Proyectos")
        page.locator("#iai-projects .thumbnail-item", has_text=project["name"]).first.click()
        expect(page.get_by_text(f"Proyecto: {project['name']}")).to_be_visible()

    switch(second)
    ui.tab("Bocetos")
    expect(indications).to_have_value("")
    expect(page.get_by_role("tab", name="Composición")).to_be_disabled()  # B aún sin boceto
    switch(first)
    ui.tab("Composición")
    expect(page.locator("#iai-composition-indications textarea")).to_have_value("")
    expect(page.locator("#iai-use-audit input")).not_to_be_checked()
