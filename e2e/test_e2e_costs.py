"""Pestaña Costes: simulación excluida por defecto, filtros, CSV y alcance global."""

import httpx
from conftest import UI, Projects
from playwright.sync_api import expect


def test_costs_tab(ui: UI, projects: Projects, api: httpx.Client) -> None:
    page = ui.page
    project = projects.create("costes")
    url = project["url"]
    brief = api.post(f"{url}/briefs").json()["brief"]
    api.post(f"{url}/briefs/{brief['id']}/approve")
    api.post(f"{url}/renders/drafts", json={"n": 2})

    ui.activate(project["name"])
    ui.tab("Costes")
    expect(page.get_by_text(f"Costes de IA de «{project['name']}»")).to_be_visible()
    calls = page.locator(".iai-kpi", has_text="Llamadas").locator("strong")
    expect(calls).to_have_text("0")  # todo es simulado: oculto por defecto
    expect(page.get_by_text("llamada(s) simulada(s) ocultas")).to_be_visible()

    page.get_by_label("Incluir simulación (modo mock)").check()
    expect(calls).to_have_text("2")  # brief + lote de bocetos

    page.locator("#iai-cost-role-f input").click()
    page.get_by_role("option", name="FAST_DRAFT").click()
    expect(
        page.locator("#iai-cost-table").get_by_text("PROMPT_ENGINEER", exact=True)
    ).to_have_count(0)
    with page.expect_download() as download:
        page.locator("#iai-cost-csv").click()
    with open(download.value.path(), encoding="utf-8-sig") as file:
        lines = file.read().splitlines()
    assert lines[0].startswith("Fecha (UTC);") and len(lines) == 2

    page.get_by_label("Todos los proyectos").check()
    expect(page.get_by_text("Costes de IA de todos los proyectos")).to_be_visible()
    expect(page.locator("#iai-cost-project")).to_be_visible()
