import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import gradio as gr
import httpx
import pytest

from shared.models import (
    AuditCheck,
    AuditDeviation,
    AuditReport,
    BriefStatus,
    DesignBrief,
    DesignBriefContent,
    DimensionsCm,
    FurnitureItem,
    ImagePrompts,
    ProjectMetadata,
    RenderAudit,
    RenderRecord,
    RenderStage,
    RenderStatus,
    utc_now,
)
from shared.roles import Role
from ui.api_client import AI_AUDIT_TIMEOUT_S, AI_TIMEOUT_S, BackendClient
from ui.studio_views import (
    approved_brief,
    audit_markdown,
    brief_choices,
    brief_markdown,
    cost_hint,
    euros,
    latest_brief,
    needs_confirmation,
    render_caption,
    render_detail_md,
    renders_of,
    selected_choices,
)
from ui.tabs.studio import build_studio_tab, describe, estimate

ROLES = {
    RenderStage.DRAFT: Role.FAST_DRAFT,
    RenderStage.COMPOSITION: Role.STRUCTURAL_COMPOSER,
    RenderStage.FINAL: Role.PHOTOREALISTIC_RENDERER,
}


def brief(version: int, status: BriefStatus = BriefStatus.PROPOSED, **extra) -> DesignBrief:
    content = DesignBriefContent(
        title="Salón verde", summary="Sofá en L <pana>", spatial_constraints=["Paso libre 90 cm"],
        furniture=[FurnitureItem(
            name="Sofá", reference_asset_id=None, placement="Pared norte", keep_exact=True,
            dimensions_cm=DimensionsCm(width_cm=285, depth_cm=160, height_cm=None),
        )],
        palette=["verde oliva"], materials=["pana"], lighting="Cálida", camera="Desde la puerta",
        image_prompts=ImagePrompts(fast_draft="fast", structural_composer="struct",
                                   photorealistic_renderer="photo"),
        open_questions=["¿Alfombra?"],
    )  # fmt: skip
    return DesignBrief(version=version, status=status, content=content, **extra)


def render(
    stage: RenderStage, status: RenderStatus = RenderStatus.GENERATED, minutes: int = 0, **extra
) -> RenderRecord:
    return RenderRecord(
        id=uuid4(), stage=stage, status=status, role=ROLES[stage], deployment="dep",
        brief_id=uuid4(), brief_version=1, prompt="prompt exacto", batch_id=uuid4(),
        size="1536x1024", quality="low", cost_eur=0.0105,
        created_at=utc_now() + timedelta(minutes=minutes), **{"input_asset_ids": []} | extra,
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
    return ProjectMetadata(
        id=uuid4(), name="Salón", space_type="salon", created_at=now, updated_at=now, **extra
    )


# --- Presentación ---------------------------------------------------------------------------


def test_costs_and_confirmation_threshold() -> None:
    assert euros(None) == "sin precio" and euros(0.0105) == "0.0105 €"
    assert cost_hint(0.095, "mock") == "Simulación: sin coste"
    assert cost_hint(0.095, "azure") == "Azure: ≈ 0.095 €"
    assert not needs_confirmation("mock", 10)
    assert not needs_confirmation("azure", 0.05)  # el umbral no se incluye
    assert needs_confirmation("azure", 0.06)


@pytest.mark.parametrize(
    ("action", "cost"),
    [
        ({"kind": "brief"}, 0.05),
        ({"kind": "audit"}, 0.25),
        ({"kind": "boceto", "n": 3}, 0.045),
        ({"kind": "render_final"}, 0.095),
        ({"kind": "reject_render", "stage": "composicion"}, 0.035),
    ],
)
def test_action_estimates(action: dict, cost: float) -> None:
    assert estimate(action) == pytest.approx(cost)
    assert describe(action)


def test_brief_helpers() -> None:
    v1 = brief(1, BriefStatus.APPROVED)
    v2 = brief(2, edited_by_user=True)
    p = project(briefs=[v1, v2])
    assert latest_brief(p) is v2 and approved_brief(p) is v1
    assert [label for label, _ in brief_choices(p)] == ["v2 · propuesto · editado", "v1 · aprobado"]
    assert latest_brief(project()) is None and approved_brief(project()) is None


def test_brief_markdown_escapes_and_keeps_unknown_dimensions() -> None:
    text = brief_markdown(brief(1, feedback="Más luz"))
    assert "Sofá en L &lt;pana&gt;" in text
    assert "| Sofá | 285 x 160 x ? | sí | Pared norte |" in text
    assert "¿Alfombra?" in text and "Más luz" in text
    assert "Aún no hay brief" in brief_markdown(None)


def test_render_helpers() -> None:
    old = render(RenderStage.DRAFT, RenderStatus.SELECTED)
    new = render(RenderStage.DRAFT, RenderStatus.SELECTED, minutes=5)
    discarded = render(RenderStage.DRAFT, RenderStatus.DISCARDED, minutes=9)
    final = render(RenderStage.FINAL, audits=[audit()])
    p = project(renders=[old, final, new, discarded])
    assert renders_of(p, RenderStage.DRAFT) == [discarded, new, old]
    assert [v for _, v in selected_choices(p, RenderStage.DRAFT)] == [str(new.id), str(old.id)]
    assert render_caption(final) == "○ generado · auditoría 82/100 · 0.0105 €"
    assert render_caption(discarded) == "- descartado · 0.0105 €"


def test_render_detail_and_audit_markdown() -> None:
    draft = render(RenderStage.DRAFT)
    retry = render(
        RenderStage.COMPOSITION, input_asset_ids=[draft.id], feedback="Sin <alfombra>",
        previous_attempt_id=uuid4(),
    )  # fmt: skip
    text = render_detail_md(project(renders=[draft, retry]), retry)
    assert f"**Entradas:** Boceto {draft.id.hex[:8]}" in text
    assert "Sustituye a" in text and "Sin &lt;alfombra&gt;" in text and "prompt exacto" in text
    assert "Selecciona una imagen" in render_detail_md(project(), None)

    report = audit_markdown(audit())
    assert "⚠️ Conforme con observaciones · 82/100" in report
    assert "| Sofá | media | 285 cm | 250 cm |" in report
    assert "Make the sofa 285 cm wide" in report
    assert "Sin auditoría" in audit_markdown(None)


# --- Cliente de la API ----------------------------------------------------------------------


async def test_studio_client_requests() -> None:
    seen: list[httpx.Request] = []
    pid, bid, rid = uuid4(), uuid4(), uuid4()
    brief_json = brief(1).model_dump(mode="json")
    render_json = render(RenderStage.DRAFT).model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/briefs") and request.method == "GET":
            return httpx.Response(200, json=[brief_json])
        if path.endswith("/renders"):
            return httpx.Response(200, json=[render_json])
        if path.endswith(("/approve", f"/briefs/{bid}")):
            return httpx.Response(200, json=brief_json)
        if path.endswith(("/select", "/discard")):
            return httpx.Response(200, json=render_json)
        return httpx.Response(200, json={"cost_eur": 0})

    client = BackendClient("http://backend.test", transport=httpx.MockTransport(handler))
    await client.list_briefs(pid)
    await client.create_brief(pid, "más verde")
    await client.update_brief(pid, bid, {"image_prompts": {"fast_draft": "x"}})
    await client.approve_brief(pid, bid)
    await client.reject_brief(pid, bid, "no", regenerate=False)
    await client.list_renders(pid, RenderStage.FINAL)
    for stage in RenderStage:
        await client.generate_renders(pid, stage, {"n": 1})
    await client.decide_render(pid, rid, select=True)
    await client.decide_render(pid, rid, select=False)
    await client.reject_render(pid, rid, "más luz", apply_audit_suggestions=False)
    await client.audit_render(pid, rid)

    assert [(r.method, r.url.path.removeprefix(f"/api/v1/projects/{pid}")) for r in seen] == [
        ("GET", "/briefs"),
        ("POST", "/briefs"),
        ("PATCH", f"/briefs/{bid}"),
        ("POST", f"/briefs/{bid}/approve"),
        ("POST", f"/briefs/{bid}/reject"),
        ("GET", "/renders"),
        ("POST", "/renders/drafts"),
        ("POST", "/renders/compositions"),
        ("POST", "/renders/final"),
        ("POST", f"/renders/{rid}/select"),
        ("POST", f"/renders/{rid}/discard"),
        ("POST", f"/renders/{rid}/reject"),
        ("POST", f"/renders/{rid}/audit"),
    ]
    assert json.loads(seen[1].content) == {"instructions": "más verde"}
    assert json.loads(seen[4].content) == {"feedback": "no", "regenerate": False}
    assert seen[5].url.params["stage"] == "render_final"
    assert json.loads(seen[11].content) == {
        "feedback": "más luz", "regenerate": True, "apply_audit_suggestions": False,
    }  # fmt: skip
    # Las llamadas de IA usan timeouts largos; la auditoría, el suyo propio.
    assert seen[1].extensions["timeout"]["read"] == AI_TIMEOUT_S
    assert seen[12].extensions["timeout"]["read"] == AI_AUDIT_TIMEOUT_S


# --- Pestaña --------------------------------------------------------------------------------


def studio_tab(p: ProjectMetadata, tmp_path: Path, mode: str = "mock"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={
                "status": "ok", "version": "0.1.0", "mode": mode, "data_dir_writable": True,
            })  # fmt: skip
        return httpx.Response(200, json=p.model_dump(mode="json"))

    client = BackendClient("http://backend.test", transport=httpx.MockTransport(handler))
    with gr.Blocks():
        active = gr.BrowserState(None)
        tab = build_studio_tab(client, tmp_path, active)
    return tab


def by_id(result: dict, elem_id: str):
    return next(v for k, v in result.items() if k.elem_id == elem_id)


def accordion_open(result: dict) -> bool:
    return next(v for k, v in result.items() if isinstance(k, gr.Accordion) and "Brief" in k.label)[
        "open"
    ]


async def test_studio_tab_without_project(tmp_path: Path) -> None:
    tab = studio_tab(project(), tmp_path)
    result = await tab.refresh_all(None)
    assert "Ningún proyecto activo" in result[tab.all_outputs[0]]


async def test_studio_tab_with_proposed_brief(tmp_path: Path) -> None:
    p = project(briefs=[brief(1)])
    result = await studio_tab(p, tmp_path, mode="azure").refresh_all(str(p.id))
    assert by_id(result, "iai-brief-version")["value"] == str(p.briefs[0].id)
    assert accordion_open(result) is True
    assert "Azure: ≈ 0.050 €" in result.values()
    assert by_id(result, "iai-gen-drafts")["interactive"] is False  # sin brief aprobado


async def test_studio_tab_with_approved_brief_and_final(tmp_path: Path) -> None:
    final = render(RenderStage.FINAL, RenderStatus.SELECTED, audits=[audit()])
    p = project(
        briefs=[brief(1, BriefStatus.APPROVED)],
        renders=[render(RenderStage.DRAFT, RenderStatus.SELECTED), final],
    )
    result = await studio_tab(p, tmp_path).refresh_all(str(p.id))
    assert accordion_open(result) is False  # el brief aprobado se pliega
    assert by_id(result, "iai-gen-drafts")["interactive"] is True
    galleries = [v for k, v in result.items() if isinstance(k, gr.Gallery)]
    assert [len(g["value"]) for g in galleries] == [1, 0, 1]
    # El visor abre el render final seleccionado, con su auditoría.
    assert any(isinstance(v, str) and "82/100" in v and "Auditoría" in v for v in result.values())
