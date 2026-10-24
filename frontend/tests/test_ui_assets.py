import json
from pathlib import Path
from uuid import uuid4

import gradio as gr
import httpx
import pytest

from shared.models import (
    Asset,
    AssetAnalysis,
    AssetKind,
    DimensionsCm,
    ReferenceAnalysis,
    utc_now,
)
from ui.api_client import BackendClient
from ui.tabs.assets import build_assets_tab
from ui.views import (
    analysis_form_values,
    analysis_status,
    asset_caption,
    asset_info_md,
    parse_analysis_form,
)

SHA = "0" * 64


def analysis(**extra) -> ReferenceAnalysis:
    data = {
        "category": "sofa", "item_name": "Sofá modular", "brand": "IKEA", "product_name": "JÄTTEBO",
        "style_tags": ["contemporáneo"], "colors": ["verde oliva"], "materials": ["pana"],
        "dimensions_cm": DimensionsCm(width_cm=285, depth_cm=160, height_cm=87),
        "dimensions_source": "nota_usuario", "summary": "Sofá", "design_relevance": "Medidas",
    } | extra  # fmt: skip
    return ReferenceAnalysis(**data)


def asset(kind: AssetKind = AssetKind.REFERENCIA, status: str | None = None) -> Asset:
    asset_id = uuid4()
    return Asset(
        id=asset_id, kind=kind, stored_name=f"{asset_id}.png", original_name="sofa.png",
        mime_type="image/png", size_bytes=2_500_000, sha256=SHA, width_px=949, height_px=535,
        analysis=AssetAnalysis(result=analysis(), status=status) if status else None,
    )  # fmt: skip


# --- Presentación ---------------------------------------------------------------------------


def test_caption_and_status() -> None:
    assert asset_caption(asset(status=None)) == "sofa.png · 949x535 · Sin indexar"
    assert analysis_status(asset(status="proposed")) == "Propuesta (IA)"
    assert analysis_status(asset(status="validated")) == "Validada ✓"
    assert asset_caption(asset(AssetKind.CAPTURA_SKETCHUP)) == "sofa.png · 949x535"
    info = asset_info_md(asset(status="validated"))
    assert "2.38 MB" in info and "949x535 px" in info and "Validada ✓" in info


def test_analysis_form_roundtrip() -> None:
    values = analysis_form_values(asset(status="proposed"))
    assert values[4:7] == ["contemporáneo", "verde oliva", "pana"]
    assert parse_analysis_form(values) == analysis()


def test_analysis_form_edits_and_normalization() -> None:
    values = analysis_form_values(asset(status="proposed"))
    values[6] = "pana de canalé ancho,  pana de canalé ancho , relieve marcado"
    values[2] = "  "
    parsed = parse_analysis_form(values)
    assert parsed.materials == ["pana de canalé ancho", "relieve marcado"]
    assert parsed.brand is None


def test_analysis_form_without_dimensions_forces_unknown_source() -> None:
    values = analysis_form_values(asset())  # sin ficha: formulario vacío
    values[1] = "Inspiración"
    parsed = parse_analysis_form(values)
    assert parsed.dimensions_cm == DimensionsCm(width_cm=None, depth_cm=None, height_cm=None)
    assert parsed.dimensions_source == "desconocido"


@pytest.mark.parametrize(
    ("index", "value", "message"),
    [(1, " ", "nombre de objeto"), (7, -1, "negativas"), (10, "desconocido", "de dónde salen")],
)
def test_analysis_form_validation(index: int, value, message: str) -> None:
    values = analysis_form_values(asset(status="proposed"))
    values[index] = value
    with pytest.raises(ValueError, match=message):
        parse_analysis_form(values)


# --- Cliente de la API -------------------------------------------------------------------------


async def test_asset_client_requests() -> None:
    seen: list[httpx.Request] = []
    body = asset(status="proposed").model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.method == "GET":
            return httpx.Response(200, json=[body])
        if request.url.path.endswith("/references/index"):
            return httpx.Response(
                200, json={"indexed": [], "skipped": [], "failed": [], "cost_eur": 0}
            )
        return httpx.Response(200 if request.method != "POST" else 201, json=body)

    client = BackendClient("http://backend.test", transport=httpx.MockTransport(handler))
    pid, aid = uuid4(), uuid4()
    await client.list_assets(pid, AssetKind.REFERENCIA)
    await client.upload_asset(pid, AssetKind.PLANO, "plano.png", b"bytes", "nota")
    await client.update_asset_note(pid, aid, "nueva")
    await client.delete_asset(pid, aid)
    await client.index_references(pid)
    await client.validate_analysis(pid, aid, analysis())

    assert [(r.method, r.url.path.removeprefix(f"/api/v1/projects/{pid}")) for r in seen] == [
        ("GET", "/assets"),
        ("POST", "/assets/plano"),
        ("PATCH", f"/assets/{aid}"),
        ("DELETE", f"/assets/{aid}"),
        ("POST", "/references/index"),
        ("PUT", f"/assets/{aid}/analysis"),
    ]
    assert seen[0].url.params["kind"] == "referencia"
    assert b'name="description"' in seen[1].content and b"nota" in seen[1].content
    assert json.loads(seen[2].content) == {"description": "nueva"}
    assert json.loads(seen[4].content) == {"force": False}
    assert json.loads(seen[5].content)["dimensions_cm"]["width_cm"] == 285


# --- Pestaña --------------------------------------------------------------------------------


async def test_assets_tab_refresh(tmp_path: Path) -> None:
    project_id = str(uuid4())
    reference, capture = asset(status="validated"), asset(AssetKind.CAPTURA_SKETCHUP)
    by_kind = {"referencia": [reference], "captura_sketchup": [capture], "plano": []}
    now = utc_now().isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/assets"):
            items = by_kind[request.url.params["kind"]]
            return httpx.Response(200, json=[a.model_dump(mode="json") for a in items])
        return httpx.Response(200, json={
            "schema_version": 2, "id": project_id, "name": "Salón",
            "description": "", "created_at": now, "updated_at": now, "assets": [], "briefs": [],
            "renders": [],
        })  # fmt: skip

    client = BackendClient("http://backend.test", transport=httpx.MockTransport(handler))
    with gr.Blocks():
        active = gr.BrowserState(None)
        tab = build_assets_tab(client, tmp_path, active)

    empty = await tab.refresh_all(None)
    assert "Ningún proyecto activo" in empty[tab.all_outputs[0]]

    result = await tab.refresh_all(project_id)
    assert result[tab.all_outputs[0]] == "### Assets de «Salón»"
    galleries = [v for k, v in result.items() if isinstance(k, gr.Gallery)]
    captions = [[item[1] for item in g["value"]] for g in galleries]
    assert captions == [["sofa.png · 949x535"], [], ["sofa.png · 949x535 · Validada ✓"]]
