import io
import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import gradio as gr
import httpx
import pytest
from PIL import Image

from shared.models import (
    RECIPE_GROUPS,
    Asset,
    AssetKind,
    AuditCheck,
    AuditDeviation,
    AuditReport,
    ProjectMetadata,
    ReferenceSheet,
    RenderAudit,
    RenderInpaint,
    RenderRecord,
    RenderStage,
    RenderStatus,
    StagePrompt,
    utc_now,
)
from shared.roles import Role
from ui.api_client import AI_AUDIT_TIMEOUT_S, AI_TIMEOUT_S, BackendClient
from ui.studio_views import (
    audit_markdown,
    audit_thumbs,
    composition_cost,
    composition_inputs,
    cost_hint,
    draft_cost,
    draft_inputs,
    draft_thumbs,
    editor_mask,
    euros,
    final_cost,
    inpaint_hint,
    needs_confirmation,
    reference_summary,
    render_caption,
    render_detail_md,
    render_inputs,
    render_title_md,
    renders_of,
    resolution_choices,
    selected_render,
    size_label,
    support_thumbs,
    thumbs_html,
)
from ui.tabs.studio import build_studio_tabs, layers_only

ROLES = {
    RenderStage.DRAFT: Role.FAST_DRAFT_MAKER,
    RenderStage.COMPOSITION: Role.COMPOSITION_BUILDER,
    RenderStage.FINAL: Role.REALISTIC_RENDERER,
}
SHA = "0" * 64


def render(
    stage: RenderStage, status: RenderStatus = RenderStatus.GENERATED, minutes: int = 0, **extra
) -> RenderRecord:
    return RenderRecord(
        id=uuid4(), stage=stage, status=status, role=ROLES[stage], deployment="dep",
        prompt="prompt exacto", batch_id=uuid4(), size="1536x1024", quality="medium",
        cost_eur=0.0105, created_at=utc_now() + timedelta(minutes=minutes),
        **{"input_asset_ids": []} | extra,
    )  # fmt: skip


REFERENCES: list[str] = []  # orden de creación de las referencias de prueba


def reference(name: str, groups: list[str]) -> Asset:
    REFERENCES.append(name)
    element = {
        "label": "x",
        "detail": "",
        "dimensions_source": "ninguna",
        "selected": False,
        "dimensions_cm": {"width_cm": None, "depth_cm": None, "height_cm": None},
    }
    recipe = {"summary": "x", **{group: [element] for group in RECIPE_GROUPS}}
    sheet = ReferenceSheet.model_validate(
        {"recipe": recipe, "selected": [f"{g}:0" for g in groups]}
    )
    asset_id = uuid4()
    return Asset(
        id=asset_id, kind=AssetKind.REFERENCIA, stored_name=f"{asset_id}.png",
        original_name=name, mime_type="image/png", size_bytes=1, sha256=SHA, sheet=sheet,
        created_at=utc_now() + timedelta(seconds=len(REFERENCES)),
    )  # fmt: skip


def audit() -> RenderAudit:
    report = AuditReport(
        verdict="conforme_con_observaciones", score=82,
        checks=[AuditCheck(aspect="proporciones", status="aviso", finding="Sofá algo corto")],
        deviations=[AuditDeviation(element="Sofá", expected="285 cm", observed="250 cm",
                                   severity="media")],
        suggested_prompt_adjustments="Make the sofa 285 cm wide", summary="Bien en general",
    )  # fmt: skip
    return RenderAudit(
        report=report, reference_asset_id=uuid4(), deployment="dep", reasoning_effort="medium",
        prompt_version="v1", cost_eur=0.21,
    )  # fmt: skip


def project(**extra) -> ProjectMetadata:
    now = utc_now()
    return ProjectMetadata(id=uuid4(), name="Salón", created_at=now, updated_at=now, **extra)


# --- Presentación ---------------------------------------------------------------------------


def test_costs_and_confirmation_threshold() -> None:
    assert euros(None) == "sin precio" and euros(0.0105) == "0.0105 €"
    assert cost_hint(0.095, "mock") == "Simulación: sin coste"
    assert cost_hint(0.095, "azure") == "Azure: ≈ 0.095 €"
    assert not needs_confirmation("mock", 10)
    assert not needs_confirmation("azure", 0.20)  # umbral de 0,20 € (B-043), no incluido
    assert needs_confirmation("azure", 0.21)


def test_draft_cost_follows_inputs_quality_and_variants() -> None:
    """Medido en el Paso 22 con 3 imágenes en calidad media: 4 bocetos = 0,142 €, 5 = 0,177 €."""
    assert draft_cost(4, "medium", 3) == pytest.approx(0.164)
    assert draft_cost(5, "medium", 3) == pytest.approx(0.173)
    assert draft_cost(4, "medium", 1) < 0.15 < draft_cost(4, "medium", 3)  # las entradas pesan
    assert draft_cost(4, "low", 3) < draft_cost(4, "high", 3)
    assert draft_cost(1, "medium", 20) == draft_cost(1, "medium", 13)  # base + 12 apoyos
    # Composición: medido en el Paso 23 con 4 imágenes en calidad media = 0,047 €.
    assert composition_cost("medium", 4) == pytest.approx(0.051)


def test_final_render_cost_and_resolutions() -> None:
    """Paso 24: precio por MP binario (primer MP, resto y 1 MP por la imagen de partida)."""
    assert final_cost("2448x1632") == pytest.approx(
        0.002 + 0.0264 + (2448 * 1632 / 1_048_576 - 1) * 0.0132 + 0.0132
    )
    assert final_cost("2448x1632") < 0.20  # sin confirmación
    assert final_cost("1024x1024", prompt=False) == pytest.approx(0.0264 + 0.0132)
    assert resolution_choices("3:2") == [
        ("1536 x 1024 · 1.6 MP", "1536x1024"),
        ("2016 x 1344 · 2.7 MP", "2016x1344"),
        ("2448 x 1632 · 4.0 MP", "2448x1632"),
    ]
    assert [size for _, size in resolution_choices("9:16")][-1] == "1440x2560"


def test_references_and_selection_helpers() -> None:
    view = reference("vista.png", ["perspectiva", "geometria"])
    sofa = reference("sofa.png", ["objetos", "colores"])
    off = reference("descartada.png", [])
    p = project(assets=[view, sofa, off])
    assert draft_inputs(p) == 2  # solo las activas
    assert composition_inputs(p) == 3  # la de partida y las dos activas como apoyo
    assert reference_summary(sofa) == "sofa.png · objetos y mobiliario (1), colores y paleta (1)"

    old = render(RenderStage.DRAFT, RenderStatus.SELECTED)
    new = render(RenderStage.DRAFT, minutes=5)
    q = project(renders=[old, new, render(RenderStage.FINAL)])
    assert renders_of(q, RenderStage.DRAFT) == [new, old]
    assert selected_render(q, RenderStage.DRAFT) == old
    assert selected_render(q, RenderStage.COMPOSITION) is None


def test_render_title_detail_and_inputs(tmp_path: Path) -> None:
    view = reference("vista.png", ["perspectiva"])
    info = StagePrompt(
        prompt="An open living room", interpretation="Conservo <la vista>",
        open_questions=["¿Alfombra?"],
    )  # fmt: skip
    draft = render(RenderStage.DRAFT, RenderStatus.SELECTED, input_asset_ids=[view.id],
                   prompt_info=info)  # fmt: skip
    p = project(assets=[view], renders=[draft])
    assert "● seleccionado" in render_title_md(draft) and "0.0105 €" in render_title_md(draft)
    detail = render_detail_md(p, draft)
    assert "Conservo &lt;la vista&gt;" in detail and "- ¿Alfombra?" in detail
    assert "prompt exacto" in detail  # el prompt enviado al modelo
    assert render_inputs(p, draft, tmp_path) == [
        (str(tmp_path / str(p.id) / "referencias" / view.stored_name), "1. vista.png")
    ]
    assert render_title_md(None).startswith("_Genera")


def test_size_label_and_final_title_without_quality() -> None:
    assert size_label("2448x1632") == "2448×1632 (3:2)"  # noqa: RUF001
    assert size_label("1536x1024") == "1536×1024 (3:2)"  # noqa: RUF001
    assert size_label("1024x1024") == "1024×1024 (1:1)"  # noqa: RUF001
    assert size_label("1920x1088") == "1920×1088"  # noqa: RUF001  (proporción no sencilla)
    draft = render(RenderStage.DRAFT)
    assert "1536×1024 (3:2) · calidad medium" in render_title_md(draft)  # noqa: RUF001
    final = render(RenderStage.FINAL).model_copy(update={"size": "2448x1632", "quality": None})
    title = render_title_md(final)
    assert "2448×1632 (3:2)" in title and "calidad" not in title  # noqa: RUF001


def test_v1_images_show_their_brief_and_audit() -> None:
    old = render(RenderStage.FINAL, brief_id=uuid4(), brief_version=2, audits=[audit()])
    assert "brief v2" in render_detail_md(project(renders=[old]), old)
    text = audit_markdown(old.audits[-1])
    assert "82/100" in text and "Sofá algo corto" in text
    assert "perspectiva o geometría" in audit_markdown(None)


def test_supports_beyond_the_limit_are_shown_in_red(tmp_path: Path) -> None:
    """Paso 23: base + 12 apoyos (los del espacio primero); los que no caben, en rojo."""
    view = reference("vista.png", ["perspectiva"])
    others = [reference(f"ref{i}.png", ["objetos"]) for i in range(12)]
    plan = reference("plano.png", ["geometria"])
    p = project(assets=[view, *others, plan])
    thumbs = draft_thumbs(p, tmp_path)
    assert [t.tone for t in thumbs] == ["start"] + [""] * 12 + ["excluded"]
    assert thumbs[1].caption.startswith("plano.png")  # geometría, antes que los demás
    assert thumbs[-1].caption == "Fuera: máx. 12 apoyos · ref11.png"
    assert draft_inputs(p) == 13
    supports = support_thumbs(p, tmp_path)  # composición: la vista también es un apoyo
    assert [t.caption.split(" ·")[0] for t in supports[:2]] == ["vista.png", "plano.png"]
    assert [t.tone for t in supports].count("excluded") == 2
    html_text = thumbs_html(thumbs)
    assert html_text.count('class="iai-thumb excluded"') == 1
    assert "/gradio_api/file=" in html_text and "&lt;" not in html_text
    assert thumbs_html([], "Nada") == '<p class="iai-muted">Nada</p>'


def test_audit_compares_every_space_reference(tmp_path: Path) -> None:
    view = reference("vista.png", ["perspectiva"])
    plan = reference("plano.png", ["geometria"])
    sofa = reference("sofa.png", ["objetos"])
    draft = render(RenderStage.DRAFT, RenderStatus.SELECTED)
    draft_asset = Asset(
        id=draft.id, kind=AssetKind.RENDER, stored_name=f"{draft.id}.png",
        original_name="boceto.png", mime_type="image/png", size_bytes=1, sha256=SHA,
    )  # fmt: skip
    p = project(assets=[view, plan, sofa, draft_asset], renders=[draft])
    captions = [t.caption for t in audit_thumbs(p, draft, tmp_path)]
    assert captions == ["Espacio · vista.png", "Espacio · plano.png", "Boceto auditado"]
    report = audit().model_copy(update={"reference_asset_ids": [view.id, plan.id]})
    assert "comparado con: vista.png, plano.png" in audit_markdown(report, p)


# --- Cliente --------------------------------------------------------------------------------


async def test_studio_client_requests() -> None:
    seen: list[httpx.Request] = []
    pid, rid = uuid4(), uuid4()
    render_json = render(RenderStage.DRAFT).model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/renders"):
            return httpx.Response(200, json=[render_json])
        if request.url.path.endswith("/select"):
            return httpx.Response(200, json=render_json)
        return httpx.Response(200, json={"cost_eur": 0})

    client = BackendClient("http://backend.test", transport=httpx.MockTransport(handler))
    await client.list_renders(pid, RenderStage.FINAL)
    for stage in RenderStage:
        await client.generate_renders(pid, stage, {"n": 1})
    await client.select_render(pid, rid)
    await client.audit_render(pid, rid, "La ventana")

    assert [(r.method, r.url.path.removeprefix(f"/api/v1/projects/{pid}")) for r in seen] == [
        ("GET", "/renders"),
        ("POST", "/renders/drafts"),
        ("POST", "/renders/compositions"),
        ("POST", "/renders/final"),
        ("POST", f"/renders/{rid}/select"),
        ("POST", f"/renders/{rid}/audit"),
    ]
    assert seen[0].url.params["stage"] == "render_final"
    assert json.loads(seen[1].content) == {"n": 1}
    assert json.loads(seen[5].content) == {"notes": "La ventana"}
    # Las llamadas de IA usan timeouts largos; la auditoría, el suyo propio.
    assert seen[1].extensions["timeout"]["read"] == AI_TIMEOUT_S
    assert seen[5].extensions["timeout"]["read"] == AI_AUDIT_TIMEOUT_S


async def test_inpaint_client_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"renders": [], "cost_eur": 0, "request_id": None})

    client = BackendClient("http://backend.test", transport=httpx.MockTransport(handler))
    pid, rid = uuid4(), uuid4()
    await client.inpaint_render(
        pid, rid, b"\x89PNG mask", "Cojines en mostaza", quality="medium", use_audit=True,
        audit_notes="", extra_instructions="Luz cálida",
    )  # fmt: skip
    [request] = seen
    assert request.url.path == f"/api/v1/projects/{pid}/renders/{rid}/inpaint"
    assert b'name="mask"; filename="mascara.png"' in request.content
    assert b'name="use_audit"\r\n\r\ntrue' in request.content
    assert b"Luz c\xc3\xa1lida" in request.content
    assert request.extensions["timeout"]["read"] == AI_TIMEOUT_S


# --- Pestaña --------------------------------------------------------------------------------


CHAIN_COST = {
    "render_id": str(uuid4()), "renders": 3, "briefs": 0, "by_role": [],
    "totals": {"calls": 5, "cost_eur": 0.2969}, "simulated_calls": 0, "simulated_cost_eur": 0,
}  # fmt: skip


def studio_tab(p: ProjectMetadata, tmp_path: Path, mode: str = "mock"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={
                "status": "ok", "version": "0.1.0", "mode": mode, "data_dir_writable": True,
            })  # fmt: skip
        if request.url.path.endswith("/cost"):
            return httpx.Response(200, json=CHAIN_COST)
        return httpx.Response(200, json=p.model_dump(mode="json"))

    client = BackendClient("http://backend.test", transport=httpx.MockTransport(handler))
    with gr.Blocks():
        active = gr.BrowserState(None)
        with gr.Tabs():
            tab = build_studio_tabs(client, tmp_path, active)
    return tab


def by_id(result: dict, elem_id: str):
    return next(v for k, v in result.items() if k.elem_id == elem_id)


def tabs(result: dict) -> dict[str, bool]:
    return {k.label: v["interactive"] for k, v in result.items() if isinstance(k, gr.Tab)}


def texts(result: dict) -> str:
    return "\n".join(v for v in result.values() if isinstance(v, str))


async def test_studio_tab_without_project(tmp_path: Path) -> None:
    tab = studio_tab(project(), tmp_path)
    result = await tab.refresh_all(None)
    assert result[tab.all_outputs[0]]["visible"] is True  # aviso: sin proyecto activo


async def test_drafts_need_active_references(tmp_path: Path) -> None:
    p = project(assets=[reference("descartada.png", [])])
    result = await studio_tab(p, tmp_path, mode="azure").refresh_all(str(p.id))
    assert "No hay referencias activas" in by_id(result, "iai-active-references")
    assert by_id(result, "iai-gen-drafts")["interactive"] is False
    assert tabs(result) == {"Composición": False, "Render Final": False}  # bloqueadas


async def test_tabs_unlock_in_order_and_show_the_selected_image(tmp_path: Path) -> None:
    """B-043: Composición con un boceto seleccionado; Render Final con una composición."""
    draft = render(RenderStage.DRAFT, RenderStatus.SELECTED, audits=[audit()])
    info = StagePrompt(prompt="A photo", interpretation="Foto", open_questions=[])
    final = render(RenderStage.FINAL, RenderStatus.SELECTED, prompt_info=info)  # de la v2
    p = project(assets=[reference("vista.png", ["perspectiva"])], renders=[draft, final])
    result = await studio_tab(p, tmp_path, mode="azure").refresh_all(str(p.id))
    assert by_id(result, "iai-gen-drafts")["interactive"] is True
    assert "Azure: ≈ 0.080 € (4 en calidad media)" in texts(result)  # 1 imagen de entrada
    assert tabs(result) == {"Composición": True, "Render Final": False}
    galleries = [by_id(result, f"iai-{s}") for s in ("drafts", "compositions", "finals")]
    assert [len(g["value"]) for g in galleries] == [1, 0, 1]
    assert by_id(result, "iai-select-drafts")["value"] == "Seleccionada ●"
    assert "**Coste acumulado de la cadena:** 0.2969 €" in by_id(result, "iai-chain-drafts")
    assert "82/100" in by_id(result, "iai-audit-report")  # auditoría del boceto seleccionado
    assert by_id(result, "iai-gen-compositions")["interactive"] is True
    assert by_id(result, "iai-gen-compositions-current")["interactive"] is False  # sin composición
    assert "Selecciona una composición" in by_id(result, "iai-start-composition")
    # Render Final (Paso 24): sin composición seleccionada solo hay versiones del render mostrado.
    assert by_id(result, "iai-gen-finals")["interactive"] is False
    assert by_id(result, "iai-gen-finals-current")["interactive"] is True
    assert by_id(result, "iai-gen-finals-variant")["interactive"] is True
    assert "Azure: ≈ 0.079 € (a 4 MP)" in texts(result)


async def test_show_render_opens_an_image_of_any_stage(tmp_path: Path) -> None:
    composition = render(RenderStage.COMPOSITION)
    p = project(renders=[composition])
    result = await studio_tab(p, tmp_path).show_render(str(p.id), str(composition.id))
    assert f"Composición `{composition.id.hex[:8]}`" in texts(result)


# --- Retoque --------------------------------------------------------------------------------


def test_mask_editor_only_reads_the_painted_layers(tmp_path: Path) -> None:
    """El fondo y la compuesta pueden estar a medio escribir en la caché de Gradio: no se leen."""
    from gradio.components.image_editor import EditorData
    from gradio.data_classes import FileData

    layer = tmp_path / "layer.png"
    Image.new("RGBA", (30, 20), (239, 68, 68, 153)).save(layer)
    broken = tmp_path / "background.png"
    broken.write_bytes(b"PNG a medias")  # no es una imagen completa
    editor = gr.ImageEditor(type="pil", format="png")
    value = layers_only(editor, EditorData(
        background=FileData(path=str(broken)), layers=[FileData(path=str(layer))],
        composite=FileData(path=str(broken)),
    ))  # fmt: skip
    assert value["background"] is None and value["composite"] is None
    assert editor_mask(value) is not None
    assert layers_only(editor, None) is None


def test_editor_mask_merges_painted_layers() -> None:
    assert editor_mask(None) is None
    assert editor_mask({"background": None, "layers": [], "composite": None}) is None
    blank = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    assert editor_mask({"layers": [blank]}) is None  # sin trazos

    stroke = blank.copy()
    stroke.paste((239, 68, 68, 153), (10, 10, 50, 50))  # pincel semitransparente
    with Image.open(io.BytesIO(editor_mask({"layers": [stroke]}))) as mask:
        assert mask.size == (300, 200) and mask.mode == "RGBA"
        assert mask.getpixel((20, 20))[3] == 255 and mask.getpixel((100, 100))[3] == 0


def test_retouch_caption_detail_and_mask_input(tmp_path: Path) -> None:
    source = render(RenderStage.COMPOSITION)
    retouch = render(
        RenderStage.COMPOSITION, input_asset_ids=[source.id],
        inpaint=RenderInpaint(source_render_id=source.id, instruction="Cojines <mostaza>",
                              mask_file="x-mascara.png", coverage=0.042),
    )  # fmt: skip
    p = project(renders=[source, retouch])
    assert render_caption(retouch) == "○ generado · retoque · 0.0105 €"
    text = render_detail_md(p, retouch)
    assert f"**Retoque de** `{source.id.hex[:8]}`" in text
    assert "Cojines &lt;mostaza&gt;" in text and "zona 4%" in text
    assert render_inputs(p, retouch, tmp_path)[-1][1] == "Máscara (blanco = zona retocada)"


@pytest.mark.parametrize(
    ("stage", "mode", "hint"),
    [
        (None, "azure", None),
        (RenderStage.DRAFT, "azure", None),
        (RenderStage.COMPOSITION, "azure", "Azure: ≈ 0.035 €"),
        (RenderStage.COMPOSITION, "mock", "Simulación: sin coste"),
        (RenderStage.FINAL, "azure", None),  # solo composiciones (B-038)
    ],
)
def test_inpaint_hint(stage: RenderStage | None, mode: str, hint: str | None) -> None:
    assert inpaint_hint(stage, mode) == hint
