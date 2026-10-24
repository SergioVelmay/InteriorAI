"""Pipelines de texto y ciclo HITL de los briefs, de extremo a extremo (cliente mock espía)."""

import io
from collections.abc import Callable

import pytest
from conftest import image_bytes, mark_legacy
from fastapi.testclient import TestClient
from PIL import Image

from app.foundry import (
    FoundryRateLimitError,
    MockFoundryClient,
    TextRequest,
    TextResult,
)
from shared.roles import Role


class SpyClient(MockFoundryClient):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[tuple[Role, TextRequest]] = []
        self.fail_with: Exception | None = None
        self.override_data: dict | None = None

    async def _complete_text(self, role: Role, request: TextRequest) -> TextResult:
        self.requests.append((role, request))
        if self.fail_with is not None:
            raise self.fail_with
        result = await super()._complete_text(role, request)
        if self.override_data is not None:
            return result.model_copy(update={"data": self.override_data})
        return result


@pytest.fixture
def api(make_api: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DEPLOYMENT_ROLE_CONTEXT_MANAGER", "gpt-6-luna")
    monkeypatch.setenv("DEPLOYMENT_ROLE_PROMPT_ENGINEER", "gpt-6.1-sol")
    return make_api()


@pytest.fixture
def spy(api: TestClient) -> SpyClient:
    client = SpyClient()
    api.app.state.foundry.inner = client
    return client


@pytest.fixture
def project(api: TestClient) -> dict:
    body = {
        "name": "Salón-cocina-comedor",
        "description": "Sofá en L junto a la península; tonos verdes y madera clara.",
    }
    pid = api.post("/api/v1/projects", json=body).json()["id"]
    url = f"/api/v1/projects/{pid}"

    def upload(kind: str, content: bytes, name: str, description: str = "") -> dict:
        response = api.post(
            f"{url}/assets/{kind}",
            files={"file": (name, content)},
            data={"description": description},
        )
        assert response.status_code == 201, response.text
        return response.json()

    project = {
        "id": pid,
        "url": url,
        "capture": upload(
            "referencia", image_bytes(size=(1600, 900)), "vista.png", "Vista del sofá"
        ),
        "plan": upload("referencia", image_bytes(size=(800, 600), color="#dddddd"), "plano.png"),
        "product": upload(
            "referencia", image_bytes(color="#556b2f"), "planificador.png", "285 x 160 x 87 cm"
        ),
        "inspiration": upload("referencia", image_bytes(color="#6b8e23"), "inspiracion.jpg"),
    }
    # Proyecto migrado de la v1: la captura y el plano conservan su tipo anterior (B-028).
    legacy = {project["capture"]["id"]: "captura_sketchup", project["plan"]["id"]: "plano"}
    mark_legacy(api, pid, legacy)
    return project


def image_size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size


# --- Referencias -------------------------------------------------------------------------


def test_index_references(api: TestClient, spy: SpyClient, project: dict) -> None:
    response = api.post(f"{project['url']}/references/index")
    assert response.status_code == 200, response.text
    body = response.json()
    assert {a["id"] for a in body["indexed"]} == {
        project["product"]["id"],
        project["inspiration"]["id"],
    }
    assert body["skipped"] == [] and body["failed"] == []
    assert body["cost_eur"] > 0
    assert body["request_id"] == response.headers["x-request-id"]
    for asset in body["indexed"]:
        assert asset["analysis"]["status"] == "proposed"
        assert asset["analysis"]["prompt_version"].startswith("context_manager@")

    assert len(spy.requests) == 2
    for role, request in spy.requests:
        assert role is Role.CONTEXT_MANAGER
        assert request.schema_name == "ficha_referencia"
        assert len(request.images) == 1
        assert request.images[0].mime_type == "image/jpeg"
    inputs = " ".join(r.input for _, r in spy.requests)
    assert "285 x 160 x 87 cm" in inputs
    assert "(sin nota)" in inputs


def test_index_skips_analyzed_unless_forced(api: TestClient, spy: SpyClient, project: dict) -> None:
    api.post(f"{project['url']}/references/index")
    again = api.post(f"{project['url']}/references/index").json()
    assert len(again["skipped"]) == 2 and again["indexed"] == []
    assert again["cost_eur"] == 0
    forced = api.post(
        f"{project['url']}/references/index",
        json={"asset_ids": [project["product"]["id"]], "force": True},
    ).json()
    assert [a["id"] for a in forced["indexed"]] == [project["product"]["id"]]
    assert len(spy.requests) == 3


def test_index_rejects_non_references_and_empty_projects(
    api: TestClient, spy: SpyClient, project: dict
) -> None:
    response = api.post(
        f"{project['url']}/references/index", json={"asset_ids": [project["capture"]["id"]]}
    )
    assert response.status_code == 422
    empty = api.post("/api/v1/projects", json={"name": "x"}).json()["id"]
    assert api.post(f"/api/v1/projects/{empty}/references/index").status_code == 422
    assert spy.requests == []


def test_index_reports_per_asset_failures(api: TestClient, spy: SpyClient, project: dict) -> None:
    spy.override_data = {"category": "inventada"}
    body = api.post(f"{project['url']}/references/index").json()
    assert body["indexed"] == []
    assert len(body["failed"]) == 2
    assert "esquema" in body["failed"][0]["error"]


def test_user_validates_and_edits_reference(api: TestClient, spy: SpyClient, project: dict) -> None:
    api.post(f"{project['url']}/references/index")
    product = project["product"]["id"]
    current = api.get(f"{project['url']}/assets/{product}").json()["analysis"]["result"]
    corrected = current | {
        "item_name": "Sofá modular con chaiselongue",
        "dimensions_cm": {"width_cm": 285, "depth_cm": 160, "height_cm": 87},
        "dimensions_source": "nota_usuario",
    }
    response = api.put(f"{project['url']}/assets/{product}/analysis", json=corrected)
    assert response.status_code == 200, response.text
    analysis = response.json()["analysis"]
    assert analysis["status"] == "validated"
    assert analysis["validated_at"] is not None
    assert analysis["result"]["dimensions_cm"]["width_cm"] == 285

    capture = project["capture"]["id"]
    assert api.put(f"{project['url']}/assets/{capture}/analysis", json=corrected).status_code == 422

    patched = api.patch(f"{project['url']}/assets/{capture}", json={"description": "  Vista 2  "})
    assert patched.json()["description"] == "Vista 2"


# --- Briefs ---------------------------------------------------------------------------------


def test_brief_context_and_creation(api: TestClient, spy: SpyClient, project: dict) -> None:
    api.post(f"{project['url']}/references/index")
    spy.requests.clear()

    response = api.post(f"{project['url']}/briefs", json={"instructions": "Prueba tonos oliva"})
    assert response.status_code == 201, response.text
    body = response.json()
    brief = body["brief"]
    assert brief["version"] == 1
    assert brief["status"] == "propuesto"
    assert brief["prompt_version"].startswith("prompt_engineer@")
    # capturas primero y después planos, ambos como imagen
    assert brief["source_asset_ids"] == [project["capture"]["id"], project["plan"]["id"]]
    assert set(brief["reference_asset_ids"]) == {
        project["product"]["id"],
        project["inspiration"]["id"],
    }
    assert not any("no es una imagen" in w for w in brief["warnings"])
    assert brief["content"]["furniture"][0]["reference_asset_id"] is None  # id inventado → null
    assert body["cost_eur"] > 0

    [(role, request)] = spy.requests
    assert role is Role.PROMPT_ENGINEER
    assert request.schema_name == "brief_diseno"
    assert len(request.images) == 2  # captura + plano; las referencias van como texto
    assert image_size(request.images[0].data) == (1024, 576)
    assert "Sofá en L junto a la península" in request.input
    assert project["product"]["id"] in request.input  # ficha como texto, con su id
    assert "285 x 160 x 87 cm" in request.input
    assert "Prueba tonos oliva" in request.input


def test_brief_without_v1_images_uses_the_oldest_reference_as_base(
    api: TestClient, spy: SpyClient
) -> None:
    pid = api.post("/api/v1/projects", json={"name": "Dormitorio"}).json()["id"]
    url = f"/api/v1/projects/{pid}"
    ids = [
        api.post(f"{url}/assets/referencia", files={"file": (name, image_bytes(color=color))})
        .json()["id"]
        for name, color in (("vista.png", "#b45309"), ("cama.png", "#556b2f"))
    ]  # fmt: skip

    brief = api.post(f"{url}/briefs").json()["brief"]
    assert brief["source_asset_ids"] == [ids[0]]  # la más antigua, como imagen
    assert brief["reference_asset_ids"] == [ids[1]]  # el resto, como fichas
    [(_, request)] = spy.requests
    assert len(request.images) == 1
    assert "Imagen 1: Referencia 'vista.png'" in request.input


def test_brief_warns_about_unindexed_references(
    api: TestClient, spy: SpyClient, project: dict
) -> None:
    brief = api.post(f"{project['url']}/briefs").json()["brief"]
    assert sum("no está indexada" in w for w in brief["warnings"]) == 2


def test_brief_requires_some_input(api: TestClient, spy: SpyClient) -> None:
    pid = api.post("/api/v1/projects", json={"name": "x"}).json()["id"]
    response = api.post(f"/api/v1/projects/{pid}/briefs")
    assert response.status_code == 422
    assert spy.requests == []


def test_edit_approve_and_lock(api: TestClient, spy: SpyClient, project: dict) -> None:
    brief = api.post(f"{project['url']}/briefs").json()["brief"]
    url = f"{project['url']}/briefs/{brief['id']}"

    edited = api.patch(url, json={"image_prompts": {"fast_draft": "Olive green corduroy sofa"}})
    assert edited.status_code == 200, edited.text
    content = edited.json()["content"]
    assert content["image_prompts"]["fast_draft"] == "Olive green corduroy sofa"
    assert content["image_prompts"]["photorealistic_renderer"] == "mock"
    assert edited.json()["edited_by_user"] is True

    approved = api.post(f"{url}/approve")
    assert approved.json()["status"] == "aprobado"
    assert approved.json()["decided_at"] is not None

    assert api.patch(url, json={"title": "Otro"}).status_code == 409
    assert api.post(f"{url}/approve").status_code == 409
    assert api.post(f"{url}/reject", json={"feedback": "x"}).status_code == 409


def test_reject_regenerates_with_feedback(api: TestClient, spy: SpyClient, project: dict) -> None:
    first = api.post(f"{project['url']}/briefs", json={"instructions": "Tonos verdes"}).json()[
        "brief"
    ]
    spy.requests.clear()

    response = api.post(
        f"{project['url']}/briefs/{first['id']}/reject",
        json={"feedback": "El sofá debe ser de pana, no de lino"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rejected"]["status"] == "rechazado"
    assert body["rejected"]["feedback"] == "El sofá debe ser de pana, no de lino"
    new = body["new_brief"]
    assert new["version"] == 2
    assert new["parent_id"] == first["id"]
    assert new["instructions"] == "Tonos verdes"

    [(_, request)] = spy.requests
    assert "El sofá debe ser de pana, no de lino" in request.input
    assert "Versión anterior (v1)" in request.input

    assert api.post(f"{project['url']}/briefs/{first['id']}/approve").status_code == 409


def test_reject_without_regenerate(api: TestClient, spy: SpyClient, project: dict) -> None:
    brief = api.post(f"{project['url']}/briefs").json()["brief"]
    body = api.post(
        f"{project['url']}/briefs/{brief['id']}/reject",
        json={"feedback": "No", "regenerate": False},
    ).json()
    assert body["new_brief"] is None
    assert body["cost_eur"] == 0
    assert (
        api.post(f"{project['url']}/briefs/{brief['id']}/reject", json={"feedback": ""}).status_code
        == 422
    )


def test_approving_a_new_version_supersedes_the_previous(
    api: TestClient, spy: SpyClient, project: dict
) -> None:
    v1 = api.post(f"{project['url']}/briefs").json()["brief"]
    api.post(f"{project['url']}/briefs/{v1['id']}/approve")
    v2 = api.post(f"{project['url']}/briefs").json()["brief"]
    api.post(f"{project['url']}/briefs/{v2['id']}/approve")

    briefs = api.get(f"{project['url']}/briefs").json()
    assert [(b["version"], b["status"]) for b in briefs] == [(2, "aprobado"), (1, "reemplazado")]
    assert api.get(f"{project['url']}/briefs/{v1['id']}").json()["status"] == "reemplazado"


def test_brief_not_found(api: TestClient, project: dict) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert api.get(f"{project['url']}/briefs/{missing}").status_code == 404
    assert api.post(f"{project['url']}/briefs/{missing}/approve").status_code == 404


# --- Errores de la IA y telemetría -------------------------------------------------------------


def test_foundry_errors_are_translated(api: TestClient, spy: SpyClient, project: dict) -> None:
    spy.fail_with = FoundryRateLimitError("Cuota de Azure agotada (429)", role=Role.PROMPT_ENGINEER)
    response = api.post(f"{project['url']}/briefs")
    assert response.status_code == 429
    assert "Cuota" in response.json()["detail"]
    assert api.get(f"{project['url']}/briefs").json() == []


def test_invalid_model_output_is_502(api: TestClient, spy: SpyClient, project: dict) -> None:
    spy.override_data = {"title": "incompleto"}
    response = api.post(f"{project['url']}/briefs")
    assert response.status_code == 502
    assert "esquema" in response.json()["detail"]


def test_pipeline_calls_are_in_project_telemetry(
    api: TestClient, spy: SpyClient, project: dict
) -> None:
    index = api.post(f"{project['url']}/references/index")
    brief = api.post(f"{project['url']}/briefs")
    costs = api.get(f"{project['url']}/costs").json()
    by_role = {g["key"]: g for g in costs["by_role"]}
    assert by_role["CONTEXT_MANAGER"]["calls"] == 2
    assert by_role["PROMPT_ENGINEER"]["calls"] == 1
    request_ids = {r["request_id"] for r in costs["records"]}
    assert request_ids == {index.headers["x-request-id"], brief.headers["x-request-id"]}
    assert costs["totals"]["cost_eur"] == pytest.approx(
        index.json()["cost_eur"] + brief.json()["cost_eur"], abs=1e-6
    )
