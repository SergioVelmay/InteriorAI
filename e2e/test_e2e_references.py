"""Pestaña Referencias: subir con notas y analizar de una en una, guardar la ficha, descartar
y reactivar una referencia, volver a analizar y rechazar un PDF (B-028 a B-030)."""

import re
from pathlib import Path

from conftest import UI, Projects
from PIL import Image
from playwright.sync_api import expect

GROUPS = 12  # grupos de la receta; el mock devuelve un elemento por grupo y lo marca


def test_references_flow(ui: UI, projects: Projects, tmp_path: Path) -> None:
    page = ui.page
    project = projects.create("referencias", capture=False, reference=False)
    Image.new("RGB", (949, 535), "#556b2f").save(tmp_path / "sofa-planificador.png")
    (tmp_path / "plano.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")

    ui.activate(project["name"])
    ui.tab("Referencias")
    expect(page.get_by_text("Assets de")).to_have_count(0)  # sin título (B-028)

    # Solo imágenes: el navegador filtra el PDF o el backend lo rechaza (415).
    file = page.locator("#iai-reference-file input[type=file]")
    file.set_input_files(str(tmp_path / "plano.pdf"))
    page.locator("#iai-reference-upload").click()
    rejected = page.get_by_text(re.compile("Formato no admitido|Añade una imagen"))
    expect(rejected.first).to_be_visible()

    # Subir + anotar + analizar, de una en una.
    file.set_input_files(str(tmp_path / "sofa-planificador.png"))
    page.locator("#iai-reference-upload-notes textarea").fill("Con estas medidas: 285 x 160 cm")
    page.locator("#iai-reference-upload").click()
    ui.toast("Receta lista")
    item = page.locator(".iai-gallery .thumbnail-item", has_text="sofa-planificador")
    expect(item).to_contain_text(f"Activa · {GROUPS} marcado(s)")
    # Paso 23: la casilla muestra el nombre; el detalle, en el tooltip.
    expect(page.locator("#iai-sheet-objetos label").first).to_have_attribute(
        "title", re.compile(".")
    )
    expect(page.locator("#iai-reference-notes textarea")).to_have_value(
        "Con estas medidas: 285 x 160 cm"
    )

    # Descartar = desmarcar todo y guardar; se reactiva marcando un grupo.
    page.get_by_role("button", name="Desmarcar todo").click()
    page.locator("#iai-save-sheet").click()
    ui.toast("la referencia queda descartada")
    expect(item).to_contain_text("Descartada")
    page.locator("#iai-sheet-group-objetos input").check()
    expect(page.locator("#iai-sheet-objetos input").first).to_be_checked()  # grupo = todo
    page.locator("#iai-save-sheet").click()
    ui.toast("Ficha guardada: 1 elemento(s) marcado(s)")
    expect(item).to_contain_text("Activa · 1 marcado(s)")

    # Volver a analizar con otras notas: la ficha vuelve a marcar lo que piden.
    page.locator("#iai-reference-notes textarea").fill("Quédate con el color")
    page.locator("#iai-reference-reanalyze").click()
    ui.toast("Receta lista")
    expect(item).to_contain_text(f"Activa · {GROUPS} marcado(s)")
