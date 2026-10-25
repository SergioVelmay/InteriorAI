"""Pestaña Costes IA: solo gasto real (B-031). En mock todo es simulado, así que se comprueba el
estado sin gasto, el alcance global y la tabla de precios; los gráficos, el registro, su
detalle y el CSV con datos se prueban en `frontend/tests/test_ui_costs.py`."""

import httpx
from conftest import UI, Projects
from playwright.sync_api import expect


def test_costs_tab(ui: UI, projects: Projects, api: httpx.Client) -> None:
    page = ui.page
    project = projects.create("costes")
    url = project["url"]
    brief = api.post(f"{url}/briefs").json()["brief"]
    api.post(f"{url}/briefs/{brief['id']}/approve")
    api.post(f"{url}/renders/drafts", json={"n": 2})  # llamadas simuladas: no son gasto real

    ui.activate(project["name"])
    ui.tab("Costes IA")
    calls = page.locator(".iai-kpi", has_text="Llamadas").locator("strong")
    expect(calls).to_have_text("0")
    expect(page.get_by_text("Todavía no hay llamadas reales")).to_be_visible()
    expect(page.get_by_label("Incluir simulación (modo mock)")).to_have_count(0)  # ya no existe

    page.get_by_label("Todos los proyectos").check()
    expect(page.locator("#iai-cost-project")).to_be_visible()

    page.get_by_text("Precios vigentes").click()
    pricing = page.locator("#iai-cost-pricing")
    expect(pricing.get_by_text("Unidades")).to_be_visible()
    expect(pricing.get_by_text("€/MPx")).to_be_visible()
