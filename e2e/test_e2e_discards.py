"""Descartes de candidatas (B-109): aspa en la miniatura, «Descartar» junto a «Seleccionar»,
desplegable «Descartados (n)» cerrado y solo con alguna, y ✓ para recuperarlas."""

import httpx
from conftest import UI, Projects
from playwright.sync_api import expect


def statuses(api: httpx.Client, project: dict) -> list[str]:
    renders = api.get(f"{project['url']}/renders", params={"stage": "boceto"}).json()
    return sorted(r["status"] for r in renders)


def test_discard_and_restore_drafts(ui: UI, projects: Projects, api: httpx.Client) -> None:
    page = ui.page
    project = projects.create("descartes")
    ui.activate(project["name"])
    ui.tab("Bocetos")
    page.locator("#iai-gen-drafts").click()
    ui.toast("Boceto: 4 imagen(es)")
    thumbs = page.locator("#iai-drafts .thumbnail-item")
    expect(thumbs).to_have_count(4)
    box = page.locator("#iai-discarded-box-drafts")
    expect(box).to_be_hidden()  # sin descartadas, sin desplegable

    # La seleccionada no tiene aspa ni «Descartar»; las demás sí.
    thumbs.nth(0).click()
    page.locator("#iai-select-drafts").click()
    ui.toast("Imagen seleccionada (boceto)")
    expect(page.locator("#iai-discard-drafts")).to_be_hidden()
    expect(page.locator("#iai-drafts .thumbnail-item .iai-thumb-action")).to_have_count(3)

    # Aspa en una miniatura: pasa a «Descartados (1)», cerrado.
    thumbs.nth(1).locator(".iai-thumb-action").click()
    ui.toast("Imagen descartada")
    expect(thumbs).to_have_count(3)
    expect(box).to_be_visible()
    expect(box.locator("button.label-wrap")).to_contain_text("Descartados (1)")
    expect(page.locator("#iai-drafts-discarded")).to_be_hidden()  # cerrado

    # «Descartar» desde el visor.
    thumbs.nth(2).click()
    page.locator("#iai-discard-drafts").click()
    expect(box.locator("button.label-wrap")).to_contain_text("Descartados (2)")
    expect(thumbs).to_have_count(2)
    assert statuses(api, project) == ["descartado", "descartado", "generado", "seleccionado"]

    # ✓: vuelve a las candidatas; sin descartadas, el desplegable desaparece.
    box.locator("button.label-wrap").click()
    restore = page.locator("#iai-drafts-discarded .thumbnail-item .iai-thumb-action")
    expect(restore).to_have_count(2)
    restore.first.click()
    ui.toast("Imagen recuperada")
    expect(thumbs).to_have_count(3)
    restore.first.click()
    expect(box).to_be_hidden()
    expect(thumbs).to_have_count(4)
    assert statuses(api, project) == ["generado", "generado", "generado", "seleccionado"]
