"""Pestaña Assets: subir, rechazar un PDF, indexar, validar la ficha y borrar."""

import re
from pathlib import Path

from conftest import UI, Projects
from PIL import Image
from playwright.sync_api import expect


def test_assets_flow(ui: UI, projects: Projects, tmp_path: Path) -> None:
    page = ui.page
    project = projects.create("assets", capture=False, reference=False)
    Image.new("RGB", (1600, 900), "#b45309").save(tmp_path / "captura-salon.png")
    Image.new("RGB", (949, 535), "#556b2f").save(tmp_path / "sofa-planificador.png")
    Image.new("RGB", (700, 700), "#6b8e23").save(tmp_path / "inspiracion.jpg")
    (tmp_path / "plano.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")

    ui.activate(project["name"])
    ui.tab("Assets")
    expect(page.get_by_text(f"Assets de «{project['name']}»")).to_be_visible()

    # Un solo tipo de imagen (B-028): la captura también es una referencia.
    files = page.locator("#iai-referencia-files input[type=file]")
    files.set_input_files(str(tmp_path / "captura-salon.png"))
    page.locator("#iai-referencia-upload").click()
    ui.toast("1 imagen(es) subida(s)")

    # Solo imágenes: el navegador filtra el PDF o el backend lo rechaza (415).
    files.set_input_files(str(tmp_path / "plano.pdf"))
    page.locator("#iai-referencia-upload").click()
    rejected = page.get_by_text(re.compile("Formato no admitido|Añade al menos una imagen"))
    expect(rejected.first).to_be_visible()

    files.set_input_files(
        [str(tmp_path / "sofa-planificador.png"), str(tmp_path / "inspiracion.jpg")]
    )
    page.get_by_label("Nota para las imágenes subidas (opcional)").last.fill("285 x 160 x 87 cm")
    page.locator("#iai-referencia-upload").click()
    ui.toast("2 imagen(es) subida(s)")
    expect(page.locator(".iai-gallery .thumbnail-item", has_text="Sin indexar")).to_have_count(3)

    page.locator("#iai-index-references").click()
    ui.toast("Indexadas: 3")
    expect(page.locator(".iai-gallery .thumbnail-item", has_text="Propuesta (IA)")).to_have_count(3)

    page.locator(".iai-gallery .thumbnail-item", has_text="sofa-planificador").click()
    note = page.locator("#iai-referencia-note textarea")
    expect(note).to_have_value("285 x 160 x 87 cm")
    note.fill("JÄTTEBO 285 x 160 x 87 cm")
    page.get_by_role("button", name="Guardar nota").last.click()
    ui.toast("Nota guardada")
    page.locator("#iai-ficha-item textarea").fill("Sofá modular con chaiselongue")
    page.locator("#iai-ficha-materials textarea").fill("pana de canalé ancho")
    page.locator("#iai-validate-ficha").click()
    ui.toast("Ficha validada")
    expect(page.locator(".iai-gallery .thumbnail-item", has_text="Validada ✓")).to_have_count(1)

    page.locator(".iai-gallery .thumbnail-item", has_text="inspiracion").click()
    page.get_by_role("button", name="Mover a la papelera").last.click()
    page.get_by_role("button", name="Confirmar: mover a la papelera").last.click()
    ui.toast("Imagen movida a la papelera")
    expect(page.locator(".iai-gallery .thumbnail-item", has_text="inspiracion")).to_have_count(0)
