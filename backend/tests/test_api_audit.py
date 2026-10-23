"""Auditoría geométrica a demanda y rechazo con comentarios (cliente mock espía)."""

import io
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_api_renders import approve_brief, new_project, run, select

from app.foundry import (
    FoundryIncompleteError,
    ImageEditRequest,
    ImageResult,
    MockFoundryClient,
    TextRequest,
    TextResult,
    Usage,
)
from shared.roles import Role


class SpyClient(MockFoundryClient):
    def __init__(self) -> None:
        super().__init__()
        self.texts: list[tuple[Role, TextRequest]] = []
        self.edits: list[tuple[Role, ImageEditRequest]] = []
        self.audit_suggestions = "Make the corduroy ribs slightly finer."
        self.fail_audit = False

    async def _complete_text(self, role: Role, request: TextRequest) -> TextResult:
        self.texts.append((role, request))
        if role is Role.GEOMETRIC_AUDITOR and self.fail_audit:
            raise FoundryIncompleteError(
                "Respuesta incompleta (motivo: max_output_tokens)",
                role=role,
                usage=Usage(input_tokens=3_000, output_tokens=12_000, reasoning_tokens=11_800),
            )
        result = await super()._complete_text(role, request)
        if role is Role.GEOMETRIC_AUDITOR:
            data = dict(result.data or {})
            data["suggested_prompt_adjustments"] = self.audit_suggestions
            return result.model_copy(update={"data": data})
        return result

    async def _edit_image(self, role: Role, request: ImageEditRequest) -> ImageResult:
        self.edits.append((role, request))
        return await super()._edit_image(role, request)


@pytest.fixture
def api(make_api: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for role, name in {
        "GEOMETRIC_AUDITOR": "gpt-6-astra",
        "FAST_DRAFT": "gpt-image-2.5-flare",
        "STRUCTURAL_COMPOSER": "gpt-image-2.5-sunburst",
        "PHOTOREALISTIC_RENDERER": "FLUX.2-pro",
    }.items():
        monkeypatch.setenv(f"DEPLOYMENT_ROLE_{role}", name)
    monkeypatch.setenv("GEOMETRIC_AUDITOR_REASONING_EFFORT", "max")
    return make_api()


@pytest.fixture
def spy(api: TestClient) -> SpyClient:
    client = SpyClient()
    api.app.state.foundry.inner = client
    return client


@pytest.fixture
def chain(api: TestClient, spy: SpyClient) -> dict:
    """Proyecto con brief aprobado, boceto, composición y render final (todos seleccionados)."""
    project = new_project(api)
    project["brief"] = approve_brief(api, project)
    draft = run(api, project, "drafts", n=1)["renders"][0]
    select(api, project, draft["id"])
    composition = run(api, project, "compositions", draft_id=draft["id"])["renders"][0]
    select(api, project, composition["id"])
    final = run(api, project, "final", composition_id=composition["id"])["renders"][0]
    spy.texts.clear()
    spy.edits.clear()
    return project | {"draft": draft, "composition": composition, "final": final}


def audit(api: TestClient, chain: dict, render_id: str):
    return api.post(f"{chain['url']}/renders/{render_id}/audit")


# --- Auditoría ---------------------------------------------------------------------------------


def test_audit_final_render_against_capture(api: TestClient, spy: SpyClient, chain: dict) -> None:
    response = audit(api, chain, chain["final"]["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    report = body["audit"]
    assert report["reference_asset_id"] == chain["capture"]  # captura de origen, no la composición
    assert report["deployment"] == "gpt-6-astra"
    assert report["reasoning_effort"] == "max"
    assert report["prompt_version"].startswith("geometric_auditor@")
    assert report["report"]["verdict"] in {"conforme", "conforme_con_observaciones", "no_conforme"}
    assert body["cost_eur"] > 0
    assert report["cost_eur"] == pytest.approx(body["cost_eur"], abs=1e-6)
    assert body["render"]["audits"][-1]["id"] == report["id"]
    assert body["render"]["status"] == "generado"  # auditar no cambia el estado

    [(role, request)] = spy.texts
    assert role is Role.GEOMETRIC_AUDITOR
    assert request.schema_name == "auditoria"
    assert request.max_output_tokens == 12_000
    assert len(request.images) == 2
    for image in request.images:
        with Image.open(io.BytesIO(image.data)) as opened:
            assert max(opened.size) <= 1_536
    assert "Restricciones espaciales del brief" in request.input
    assert "Mobiliario que debe respetarse con exactitud" in request.input
    assert chain["final"]["prompt"] in request.input


def test_audit_composition_and_history(api: TestClient, spy: SpyClient, chain: dict) -> None:
    audit(api, chain, chain["composition"]["id"])
    second = audit(api, chain, chain["composition"]["id"]).json()
    assert len(second["render"]["audits"]) == 2
    assert second["audit"]["reference_asset_id"] == chain["capture"]


def test_drafts_cannot_be_audited(api: TestClient, spy: SpyClient, chain: dict) -> None:
    assert audit(api, chain, chain["draft"]["id"]).status_code == 422
    assert audit(api, chain, "00000000-0000-0000-0000-000000000000").status_code == 404
    assert spy.texts == []


def test_selection_does_not_require_audit(api: TestClient, spy: SpyClient, chain: dict) -> None:
    selected = select(api, chain, chain["final"]["id"])
    assert selected["status"] == "seleccionado"
    assert selected["audits"] == []


def test_incomplete_audit_is_502_but_billed(api: TestClient, spy: SpyClient, chain: dict) -> None:
    spy.fail_audit = True
    response = audit(api, chain, chain["final"]["id"])
    assert response.status_code == 502
    assert "incompleta" in response.json()["detail"]
    costs = api.get(f"{chain['url']}/costs").json()
    auditor = next(g for g in costs["by_role"] if g["key"] == "GEOMETRIC_AUDITOR")
    assert auditor["errors"] == 1
    # Precios de lista por el billing_factor de config/pricing.yaml
    assert auditor["cost_eur"] == pytest.approx((3_000 * 8.80 + 12_000 * 44.0) / 1e6 * 0.98463)
    renders = api.get(f"{chain['url']}/renders").json()
    assert all(r["audits"] == [] for r in renders)


# --- Rechazo con comentarios -------------------------------------------------------------------


def test_reject_with_feedback_and_audit_suggestions(
    api: TestClient, spy: SpyClient, chain: dict
) -> None:
    audit(api, chain, chain["final"]["id"])
    response = api.post(
        f"{chain['url']}/renders/{chain['final']['id']}/reject",
        json={"feedback": "El verde debe ser más oscuro y apagado"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rejected"]["status"] == "rechazado"
    assert body["rejected"]["feedback"] == "El verde debe ser más oscuro y apagado"
    [new] = body["new_renders"]
    assert new["stage"] == "render_final"
    assert new["previous_attempt_id"] == chain["final"]["id"]
    assert new["parent_render_id"] == chain["composition"]["id"]
    assert new["input_asset_ids"] == chain["final"]["input_asset_ids"]
    assert new["size"] == chain["final"]["size"]
    assert new["prompt"].startswith(chain["final"]["prompt"])
    assert "El verde debe ser más oscuro y apagado" in new["prompt"]
    assert "Make the corduroy ribs slightly finer." in new["prompt"]
    assert body["cost_eur"] > 0

    [(role, request)] = spy.edits
    assert role is Role.PHOTOREALISTIC_RENDERER
    assert request.prompt == new["prompt"]


def test_reject_without_audit_suggestions_or_regeneration(
    api: TestClient, spy: SpyClient, chain: dict
) -> None:
    audit(api, chain, chain["composition"]["id"])
    body = api.post(
        f"{chain['url']}/renders/{chain['composition']['id']}/reject",
        json={"feedback": "Más luz", "apply_audit_suggestions": False},
    ).json()
    assert "Make the corduroy" not in body["new_renders"][0]["prompt"]
    assert body["new_renders"][0]["quality"] == "medium"

    only = api.post(
        f"{chain['url']}/renders/{chain['draft']['id']}/reject",
        json={"feedback": "No", "regenerate": False},
    ).json()
    assert only["new_renders"] == []
    assert only["cost_eur"] == 0


def test_rejected_is_terminal(api: TestClient, spy: SpyClient, chain: dict) -> None:
    url = f"{chain['url']}/renders/{chain['final']['id']}"
    api.post(f"{url}/reject", json={"feedback": "No", "regenerate": False})
    assert api.post(f"{url}/select").status_code == 409
    assert api.post(f"{url}/reject", json={"feedback": "Otra vez"}).status_code == 409
    assert api.post(f"{url}/reject", json={"feedback": ""}).status_code == 422
