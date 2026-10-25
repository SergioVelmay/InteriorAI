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
    monkeypatch.setenv("DEPLOYMENT_ROLE_REFERENCE_ANALYST", "gpt-6-luna")
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


GROUPS = (
    "objetos", "decoracion", "colores", "materiales", "arquitectura", "estilo", "iluminacion",
    "perspectiva", "geometria", "ambiente", "fotografia", "otros",
)  # fmt: skip


def save_sheet(api: TestClient, project: dict, key: str, selected: list[str]):
    return api.put(
        f"{project['url']}/assets/{project[key]['id']}/sheet", json={"selected": selected}
    )


def test_analyze_one_reference_with_notes(api: TestClient, spy: SpyClient, project: dict) -> None:
    """B-029: una imagen, sus notas y su receta; la ficha se guarda desde el análisis."""
    url = f"{project['url']}/assets/{project['product']['id']}/analyze"
    response = api.post(url, json={"notes": "  Con estas medidas: 285 x 160 x 87 cm  "})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cost_eur"] > 0 and body["request_id"] == response.headers["x-request-id"]
    asset = body["asset"]
    assert asset["description"] == "Con estas medidas: 285 x 160 x 87 cm"  # notas guardadas
    sheet = asset["sheet"]
    assert sheet["prompt_version"].startswith("reference_analyst@")
    assert sheet["notes"] == asset["description"]
    assert sheet["deployment"] == "gpt-6-luna"
    assert set(sheet["recipe"]) == {"summary", *GROUPS}
    # El mock marca todo: equivale a unas notas que lo piden todo.
    assert sheet["selected"] == [f"{group}:0" for group in GROUPS]

    [(role, request)] = spy.requests
    assert role is Role.REFERENCE_ANALYST
    assert request.schema_name == "receta_referencia"
    assert len(request.images) == 1 and request.images[0].mime_type == "image/jpeg"
    assert "Con estas medidas: 285 x 160 x 87 cm" in request.input


def test_analyze_rejects_renders_and_unknown_assets(
    api: TestClient, spy: SpyClient, project: dict
) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert api.post(f"{project['url']}/assets/{missing}/analyze").status_code == 404
    empty = api.post("/api/v1/projects", json={"name": "x"}).json()["id"]
    assert api.post(f"/api/v1/projects/{empty}/references/index").status_code == 422
    assert spy.requests == []


def test_index_analyzes_pending_references(api: TestClient, spy: SpyClient, project: dict) -> None:
    """Análisis en bloque (p. ej. el reanálisis de las referencias existentes)."""
    response = api.post(f"{project['url']}/references/index")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["indexed"]) == 4  # también la captura y el plano de la v1
    assert body["skipped"] == [] and body["failed"] == []
    inputs = " ".join(r.input for _, r in spy.requests)
    assert "285 x 160 x 87 cm" in inputs and "(sin notas)" in inputs

    again = api.post(f"{project['url']}/references/index").json()
    assert len(again["skipped"]) == 4 and again["indexed"] == [] and again["cost_eur"] == 0
    forced = api.post(
        f"{project['url']}/references/index",
        json={"asset_ids": [project["product"]["id"]], "force": True},
    ).json()
    assert [a["id"] for a in forced["indexed"]] == [project["product"]["id"]]
    assert len(spy.requests) == 5


def test_index_reports_per_asset_failures(api: TestClient, spy: SpyClient, project: dict) -> None:
    spy.override_data = {"summary": "incompleta"}
    body = api.post(f"{project['url']}/references/index").json()
    assert body["indexed"] == []
    assert len(body["failed"]) == 4
    assert "esquema" in body["failed"][0]["error"]


def test_user_saves_the_sheet(api: TestClient, spy: SpyClient, project: dict) -> None:
    """B-030: «Guardar ficha»; vacía = descartada (se reactiva marcando algo)."""
    assert save_sheet(api, project, "product", ["objetos:0"]).status_code == 422  # sin receta
    api.post(f"{project['url']}/references/index")

    saved = save_sheet(api, project, "product", ["colores:0", "objetos:0"])
    assert saved.status_code == 200, saved.text
    assert saved.json()["sheet"]["selected"] == ["objetos:0", "colores:0"]  # orden de la receta
    assert save_sheet(api, project, "product", ["objetos:7"]).status_code == 422
    assert save_sheet(api, project, "product", []).json()["sheet"]["selected"] == []

    patched = api.patch(
        f"{project['url']}/assets/{project['capture']['id']}", json={"description": "  Vista  "}
    )
    assert patched.json()["description"] == "Vista"


# --- Briefs ---------------------------------------------------------------------------------


def prepared_sheets(api: TestClient, project: dict) -> None:
    """Fichas como las de un proyecto real: vista, plano, producto y una referencia descartada."""
    api.post(f"{project['url']}/references/index")
    save_sheet(api, project, "capture", ["perspectiva:0"])
    save_sheet(api, project, "plan", ["geometria:0"])
    save_sheet(api, project, "product", ["objetos:0", "materiales:0"])
    save_sheet(api, project, "inspiration", [])  # descartada: no se usa


def test_brief_context_and_creation(api: TestClient, spy: SpyClient, project: dict) -> None:
    prepared_sheets(api, project)
    spy.requests.clear()

    response = api.post(f"{project['url']}/briefs", json={"instructions": "Prueba tonos oliva"})
    assert response.status_code == 201, response.text
    body = response.json()
    brief = body["brief"]
    assert brief["version"] == 1
    assert brief["status"] == "propuesto"
    assert brief["prompt_version"].startswith("prompt_engineer@")
    # Imágenes del espacio: perspectiva primero y después geometría.
    assert brief["source_asset_ids"] == [project["capture"]["id"], project["plan"]["id"]]
    # Fichas: solo las referencias activas.
    assert brief["reference_asset_ids"] == [
        project["capture"]["id"], project["plan"]["id"], project["product"]["id"],
    ]  # fmt: skip
    assert brief["content"]["furniture"][0]["reference_asset_id"] is None  # id inventado → null
    assert body["cost_eur"] > 0

    [(role, request)] = spy.requests
    assert role is Role.PROMPT_ENGINEER
    assert request.schema_name == "brief_diseno"
    assert len(request.images) == 2
    assert image_size(request.images[0].data) == (1024, 576)
    assert "Sofá en L junto a la península" in request.input
    assert project["product"]["id"] in request.input  # ficha como texto, con su id
    assert project["inspiration"]["id"] not in request.input  # descartada
    assert '"Objetos y mobiliario"' in request.input and '"imagen_adjunta": 1' in request.input
    assert '"Colores y paleta"' not in request.input  # solo lo marcado
    assert "Prueba tonos oliva" in request.input


def test_brief_without_marked_space_uses_the_oldest_reference_as_base(
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
    assert brief["source_asset_ids"] == [ids[0]]  # sin fichas: la más antigua, como imagen
    assert brief["reference_asset_ids"] == []  # sin analizar: no son activas
    assert sum("aún no está analizada" in w for w in brief["warnings"]) == 2
    [(_, request)] = spy.requests
    assert len(request.images) == 1


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
    assert by_role["REFERENCE_ANALYST"]["calls"] == 4
    assert by_role["PROMPT_ENGINEER"]["calls"] == 1
    request_ids = {r["request_id"] for r in costs["records"]}
    assert request_ids == {index.headers["x-request-id"], brief.headers["x-request-id"]}
    assert costs["totals"]["cost_eur"] == pytest.approx(
        index.json()["cost_eur"] + brief.json()["cost_eur"], abs=1e-6
    )


def test_first_analysis_of_v1_images_adds_their_former_role(
    api: TestClient, spy: SpyClient, project: dict
) -> None:
    """Paso 21: la captura y el plano de la v1 llevan a sus notas el papel que tenían."""
    api.post(f"{project['url']}/references/index")
    notes = {
        a["id"]: a["description"]
        for a in api.get(f"{project['url']}/assets", params={"kind": "referencia"}).json()
    }
    assert notes[project["capture"]["id"]] == (
        "Vista del sofá\nQuédate con el punto de vista, la perspectiva y la geometría del espacio."
    )
    assert notes[project["plan"]["id"]] == "Quédate con las medidas y la distribución."
    assert notes[project["product"]["id"]] == "285 x 160 x 87 cm"  # las demás, intactas
    api.post(f"{project['url']}/references/index", json={"force": True})
    again = api.get(f"{project['url']}/assets/{project['plan']['id']}").json()
    assert again["description"] == "Quédate con las medidas y la distribución."  # una sola vez
