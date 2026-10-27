"""Auditoría geométrica a demanda y rechazo con comentarios (cliente mock espía)."""

import io
from collections.abc import Callable

import pytest
from conftest import mark_active
from fastapi.testclient import TestClient
from PIL import Image
from test_api_renders import new_project, run, select

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
        if role is Role.GEOMETRY_AUDITOR and self.fail_audit:
            raise FoundryIncompleteError(
                "Respuesta incompleta (motivo: max_output_tokens)",
                role=role,
                usage=Usage(input_tokens=3_000, output_tokens=12_000, reasoning_tokens=11_800),
            )
        result = await super()._complete_text(role, request)
        if role is Role.GEOMETRY_AUDITOR:
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
        "GEOMETRY_AUDITOR": "gpt-6-astra",
        "FAST_DRAFT_MAKER": "gpt-image-2.5-flare",
        "COMPOSITION_BUILDER": "gpt-image-2.5-sunburst",
        "REALISTIC_RENDERER": "FLUX.2-pro",
    }.items():
        monkeypatch.setenv(f"DEPLOYMENT_ROLE_{role}", name)
    monkeypatch.setenv("GEOMETRY_AUDITOR_REASONING_EFFORT", "max")
    return make_api()


@pytest.fixture
def spy(api: TestClient) -> SpyClient:
    client = SpyClient()
    api.app.state.foundry.inner = client
    return client


@pytest.fixture
def chain(api: TestClient, spy: SpyClient) -> dict:
    """Proyecto con boceto, composición y render final (todos seleccionados)."""
    project = new_project(api)
    draft = run(api, project, "drafts", n=1)["renders"][0]
    select(api, project, draft["id"])
    composition = run(api, project, "compositions", draft_id=draft["id"])["renders"][0]
    select(api, project, composition["id"])
    final = run(api, project, "final", composition_id=composition["id"])["renders"][0]
    spy.texts.clear()
    spy.edits.clear()
    return project | {"draft": draft, "composition": composition, "final": final}


def audit(api: TestClient, chain: dict, render_id: str, **body: str):
    return api.post(f"{chain['url']}/renders/{render_id}/audit", json=body or None)


# --- Auditoría ---------------------------------------------------------------------------------


def test_audit_draft_against_space_references(api: TestClient, spy: SpyClient, chain: dict) -> None:
    """B-046: el boceto se compara con todas las referencias activas de perspectiva o geometría
    (aquí, la vista), con las observaciones del usuario."""
    response = audit(api, chain, chain["draft"]["id"], notes="La ventana está desplazada")
    assert response.status_code == 200, response.text
    body = response.json()
    report = body["audit"]
    assert report["reference_asset_ids"] == [chain["capture"]]
    assert "reference_asset_id" not in report  # sin la v1 (Paso 33)
    assert report["notes"] == "La ventana está desplazada"
    assert report["deployment"] == "gpt-6-astra"
    assert report["reasoning_effort"] == "max"
    assert report["prompt_version"].startswith("auditor_espacio@")
    assert report["report"]["verdict"] in {"conforme", "conforme_con_observaciones", "no_conforme"}
    assert body["cost_eur"] > 0
    assert report["cost_eur"] == pytest.approx(body["cost_eur"], abs=1e-6)
    assert body["render"]["audits"][-1]["id"] == report["id"]
    assert body["render"]["status"] == "seleccionado"  # auditar no cambia el estado

    [(role, request)] = spy.texts
    assert role is Role.GEOMETRY_AUDITOR
    assert request.schema_name == "auditoria"
    assert request.max_output_tokens == 12_000
    assert len(request.images) == 2  # la vista y el boceto, en ese orden
    for image in request.images:
        with Image.open(io.BytesIO(image.data)) as opened:
            assert max(opened.size) <= 1_536
    assert "Imagen 1: referencia del espacio — «vista.png»" in request.input
    assert "Imagen 2: imagen auditada" in request.input
    assert "Lo marcado en las fichas del usuario" in request.input
    assert "La ventana está desplazada" in request.input
    assert chain["draft"]["prompt"] in request.input


def test_audit_uses_every_space_reference(api: TestClient, spy: SpyClient, chain: dict) -> None:
    pid = chain["url"].rsplit("/", 1)[1]
    mark_active(api, pid, {chain["product"]: ["geometria"], chain["inspiration"]: ["colores"]})
    report = audit(api, chain, chain["draft"]["id"]).json()["audit"]
    assert report["reference_asset_ids"] == [chain["capture"], chain["product"]]
    assert len(spy.texts[-1][1].images) == 3

    # Sin referencias del espacio: solo la imagen auditada y lo marcado.
    mark_active(api, pid, {chain["capture"]: ["colores"], chain["product"]: ["objetos"]})
    report = audit(api, chain, chain["draft"]["id"]).json()["audit"]
    assert report["reference_asset_ids"] == []
    assert len(spy.texts[-1][1].images) == 1


def test_audit_composition_and_history(api: TestClient, spy: SpyClient, chain: dict) -> None:
    audit(api, chain, chain["composition"]["id"])
    second = audit(api, chain, chain["composition"]["id"]).json()
    assert len(second["render"]["audits"]) == 2
    assert second["audit"]["reference_asset_ids"] == [chain["capture"]]


def test_audit_validation(api: TestClient, spy: SpyClient, chain: dict) -> None:
    assert audit(api, chain, "00000000-0000-0000-0000-000000000000").status_code == 404
    long_notes = audit(api, chain, chain["draft"]["id"], notes="x" * 2_001)
    assert long_notes.status_code == 422
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
    auditor = next(g for g in costs["by_role"] if g["key"] == "GEOMETRY_AUDITOR")
    assert auditor["errors"] == 1
    # Precios de lista por el billing_factor de config/pricing.yaml
    assert auditor["cost_eur"] == pytest.approx((3_000 * 8.80 + 12_000 * 44.0) / 1e6 * 0.98463)
    renders = api.get(f"{chain['url']}/renders").json()
    assert all(r["audits"] == [] for r in renders)


# --- Sin rechazo ni descarte (B-048) ------------------------------------------------------------


@pytest.mark.parametrize("action", ["reject", "discard"])
def test_reject_and_discard_were_removed(
    api: TestClient, spy: SpyClient, chain: dict, action: str
) -> None:
    url = f"{chain['url']}/renders/{chain['final']['id']}/{action}"
    assert api.post(url, json={"feedback": "No"}).status_code in {404, 405}
    assert spy.edits == []
