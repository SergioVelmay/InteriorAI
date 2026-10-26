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
    # Pasa al último proyecto actualizado, si queda alguno (B-025).
    expect(page.get_by_text(f"Proyecto: {name}")).to_have_count(0)
    expect(page.locator(".iai-gallery .thumbnail-item", has_text=name)).to_have_count(0)


def test_common_style_and_refresh(ui: UI, projects: Projects, browser) -> None:
    """Paso 27: pestaña activa en negrita (B-058); Proyectos se recarga al volver a ella
    (B-062); textos de Gradio en español con el navegador en inglés (B-063)."""
    page = ui.page
    selected = page.get_by_role("tab", name="Proyectos")
    expect(selected).to_have_css("font-weight", "600")
    expect(page.get_by_role("tab", name="Referencias")).to_have_css("font-weight", "400")

    ui.tab("Referencias")
    project = projects.create("recarga", capture=False, reference=False)  # por la API
    ui.tab("Proyectos")
    expect(page.locator("#iai-projects .thumbnail-item", has_text=project["name"])).to_be_visible()

    context = browser.new_context(locale="en-US")
    english = context.new_page()
    english.goto(page.url, wait_until="load")
    english.wait_for_selector("text=Backend conectado")
    english.get_by_role("tab", name="Referencias").click()
    expect(english.locator("#iai-reference-file")).to_contain_text("Arrastra el archivo aquí")
    context.close()
