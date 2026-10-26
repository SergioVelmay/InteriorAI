import html
import json
from pathlib import Path
from uuid import uuid4

import gradio as gr
import httpx

from shared.models import (
    RECIPE_GROUPS,
    Asset,
    AssetKind,
    ProjectMetadata,
    ReferenceRecipe,
    ReferenceSheet,
    utc_now,
)
from ui.api_client import AI_TIMEOUT_S, BackendClient
from ui.tabs.references import build_references_tab
from ui.views import (
    asset_caption,
    asset_info_md,
    element_label,
    selected_ids,
    sheet_groups,
    sheet_status,
    sheet_tooltips,
    tooltips_html,
)

SHA = "0" * 64


def element(label: str, source: str = "ninguna", dims=(None, None, None), detail: str = ""):
    return {
        "label": label, "detail": detail, "dimensions_source": source, "selected": False,
        "dimensions_cm": dict(zip(("width_cm", "depth_cm", "height_cm"), dims, strict=True)),
    }  # fmt: skip


def recipe() -> ReferenceRecipe:
    groups = {group: [] for group in RECIPE_GROUPS}
    groups["objetos"] = [
        element("Sofá JÄTTEBO", "cota_imagen", (285, 160, 87), "Chaise a la derecha"),
        element("Mesa baja", "estimada", (90, 50, None)),
    ]
    groups["colores"] = [element("Verde oliva")]
    return ReferenceRecipe.model_validate({"summary": "Sofá modular verde", **groups})


def asset(selected: list[str] | None = None, analyzed: bool = True) -> Asset:
    asset_id = uuid4()
    sheet = ReferenceSheet(recipe=recipe(), selected=selected or []) if analyzed else None
    return Asset(
        id=asset_id, kind=AssetKind.REFERENCIA, stored_name=f"{asset_id}.png",
        original_name="sofa.png", mime_type="image/png", size_bytes=2_500_000, sha256=SHA,
        width_px=949, height_px=535, description="Con estas medidas", sheet=sheet,
    )  # fmt: skip


# --- Presentación ---------------------------------------------------------------------------


def test_caption_status_and_info() -> None:
    assert sheet_status(asset(analyzed=False)) == "Sin analizar"
    assert sheet_status(asset()) == "Descartada"
    assert sheet_status(asset(["objetos:0", "colores:0"])) == "Activa · 2 marcado(s)"
    assert (
        asset_caption(asset(["objetos:0"])) == "sofa.png\n949x535 · Activa · 1 marcado(s)"
    )  # B-065
    info = asset_info_md(asset())
    assert "2.38 MB" in info and "949x535 px" in info and "Sofá modular verde" in info


def test_element_labels_mark_estimated_measures() -> None:
    sofa, table = recipe().objetos
    assert element_label(sofa) == (
        "Sofá JÄTTEBO — Chaise a la derecha (285 x 160 x 87 cm, cota en la imagen)"
    )
    assert element_label(table) == "Mesa baja (90 x 50 x ? cm, estimada)"
    assert element_label(recipe().colores[0]) == "Verde oliva"


def test_sheet_groups_and_selection() -> None:
    groups = sheet_groups(asset(["objetos:1", "colores:0"]))
    assert list(groups) == list(RECIPE_GROUPS)
    choices, marked = groups["objetos"]
    assert [element_id for _, element_id in choices] == ["objetos:0", "objetos:1"]
    assert [label for label, _ in choices] == ["Sofá JÄTTEBO", "Mesa baja"]  # solo el nombre
    assert marked == ["objetos:1"]
    assert groups["decoracion"] == ([], [])
    assert sheet_groups(None)["objetos"] == ([], [])
    assert selected_ids([["objetos:0"], None, ["colores:0"]]) == ["objetos:0", "colores:0"]


def test_sheet_details_go_to_tooltips() -> None:
    """Paso 23: la ficha muestra solo nombres; el detalle y las medidas, al pasar el ratón."""
    tips = sheet_tooltips(asset(["objetos:0"]))
    assert tips["objetos"] == [
        "Sofá JÄTTEBO — Chaise a la derecha (285 x 160 x 87 cm, cota en la imagen)",
        "Mesa baja (90 x 50 x ? cm, estimada)",
    ]
    assert tips["colores"] == ["Verde oliva"]
    assert sheet_tooltips(None) == {} and sheet_tooltips(asset(analyzed=False)) == {}
    holder = tooltips_html({"objetos": ['Sofá "L" <b>']})
    assert holder.startswith('<div data-tips="') and "<b>" not in holder
    data = html.unescape(holder.split('"', 2)[1])
    assert json.loads(data) == {"objetos": ['Sofá "L" <b>']}


# --- Cliente y pestaña --------------------------------------------------------------------------


async def test_reference_client_requests() -> None:
    seen: list[httpx.Request] = []
    body = asset().model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/analyze"):
            return httpx.Response(200, json={"asset": body, "cost_eur": 0.03, "request_id": "r"})
        if request.method == "GET":
            return httpx.Response(200, json=[body])
        return httpx.Response(200 if request.method != "POST" else 201, json=body)

    client = BackendClient("http://backend.test", transport=httpx.MockTransport(handler))
    pid, aid = uuid4(), uuid4()
    await client.list_assets(pid, AssetKind.REFERENCIA)
    await client.upload_asset(pid, AssetKind.REFERENCIA, "vista.png", b"bytes", "nota")
    await client.analyze_reference(pid, aid)
    await client.analyze_reference(pid, aid, "con estas medidas")
    await client.save_sheet(pid, aid, ["objetos:0"])
    await client.update_asset_note(pid, aid, "nueva")

    assert [(r.method, r.url.path.removeprefix(f"/api/v1/projects/{pid}")) for r in seen] == [
        ("GET", "/assets"),
        ("POST", "/assets/referencia"),
        ("POST", f"/assets/{aid}/analyze"),
        ("POST", f"/assets/{aid}/analyze"),
        ("PUT", f"/assets/{aid}/sheet"),
        ("PATCH", f"/assets/{aid}"),
    ]
    assert json.loads(seen[2].content) == {}
    assert json.loads(seen[3].content) == {"notes": "con estas medidas"}
    assert seen[3].extensions["timeout"]["read"] == AI_TIMEOUT_S
    assert json.loads(seen[4].content) == {"selected": ["objetos:0"]}


async def test_references_tab_refresh(tmp_path: Path) -> None:
    project_id = str(uuid4())
    active, pending = asset(["objetos:0"]), asset(analyzed=False)

    now = utc_now()
    project = ProjectMetadata(id=project_id, name="Salón", created_at=now, updated_at=now,
                              assets=[active, pending])  # fmt: skip

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/assets"):
            assert request.url.params["kind"] == "referencia"
            return httpx.Response(200, json=[a.model_dump(mode="json") for a in (active, pending)])
        return httpx.Response(200, json=project.model_dump(mode="json"))

    client = BackendClient("http://backend.test", transport=httpx.MockTransport(handler))
    with gr.Blocks():
        state = gr.BrowserState(None)
        tab = build_references_tab(client, tmp_path, state)

    empty = await tab.refresh_all(None)
    notice = tab.all_outputs[0]
    assert empty[notice]["visible"] is True  # sin proyecto activo

    result = await tab.refresh_all(project_id)
    assert result[notice]["visible"] is False
    warning = next(v for k, v in result.items() if k.elem_id == "iai-supports-warning")
    assert warning["visible"] is False  # caben todas
    gallery = next(v for k, v in result.items() if isinstance(k, gr.Gallery))
    assert [item[1] for item in gallery["value"]] == [
        "sofa.png\n949x535 · Activa · 1 marcado(s)",
        "sofa.png\n949x535 · Sin analizar",
    ]
