"""Pestaña Proyectos: crear, editar, recordar el proyecto activo y mover a la papelera."""

from conftest import UI, Projects
from playwright.sync_api import expect


def test_project_lifecycle(ui: UI, projects: Projects) -> None:
    page, name = ui.page, projects.name("proyectos")

    page.get_by_text("Nuevo proyecto").click()
    page.locator("#iai-new-name textarea").fill(name)
    page.get_by_role("button", name="Crear proyecto").click()
    expect(page.get_by_text(f"Proyecto: {name}")).to_be_visible()
    expect(page.locator(".iai-gallery .thumbnail-item", has_text=name)).to_be_visible()

    page.locator("#iai-project-description textarea").fill("Creado desde la prueba E2E")
    page.get_by_role("button", name="Guardar cambios").click()
    ui.toast(f"Cambios guardados en «{name}»")

    # El proyecto activo se recuerda en el navegador.
    page.reload(wait_until="load")
    expect(page.get_by_text(f"Proyecto: {name}")).to_be_visible()
    expect(page.locator("#iai-project-description textarea")).to_have_value(
        "Creado desde la prueba E2E"
    )

    page.get_by_role("button", name="Mover a la papelera").click()
    page.get_by_role("button", name="Confirmar: mover a la papelera").click()
    expect(page.get_by_text("Sin proyecto activo")).to_be_visible()
    expect(page.locator(".iai-gallery .thumbnail-item", has_text=name)).to_have_count(0)
