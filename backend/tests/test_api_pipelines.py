"""Pipelines de texto (recetas y fichas de las referencias), de extremo a extremo (cliente mock
espía)."""

import io
from collections.abc import Callable

import pytest
from conftest import image_bytes
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
    monkeypatch.setenv("DEPLOYMENT_ROLE_PROMPT_ARCHITECT", "gpt-6.1-sol")
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


# --- Errores de la IA y telemetría -------------------------------------------------------------


def test_foundry_errors_are_translated(api: TestClient, spy: SpyClient, project: dict) -> None:
    spy.fail_with = FoundryRateLimitError(
        "Cuota de Azure agotada (429)", role=Role.REFERENCE_ANALYST
    )
    asset_url = f"{project['url']}/assets/{project['product']['id']}"
    response = api.post(f"{asset_url}/analyze")
    assert response.status_code == 429
    assert "Cuota" in response.json()["detail"]
    assert api.get(asset_url).json()["sheet"] is None


def test_invalid_model_output_is_502(api: TestClient, spy: SpyClient, project: dict) -> None:
    spy.override_data = {"summary": "incompleta"}
    response = api.post(f"{project['url']}/assets/{project['product']['id']}/analyze")
    assert response.status_code == 502
    assert "esquema" in response.json()["detail"]


def test_pipeline_calls_are_in_project_telemetry(
    api: TestClient, spy: SpyClient, project: dict
) -> None:
    index = api.post(f"{project['url']}/references/index")
    costs = api.get(f"{project['url']}/costs").json()
    by_role = {g["key"]: g for g in costs["by_role"]}
    assert by_role["REFERENCE_ANALYST"]["calls"] == 4
    assert {r["request_id"] for r in costs["records"]} == {index.headers["x-request-id"]}
    assert costs["totals"]["cost_eur"] == pytest.approx(index.json()["cost_eur"], abs=1e-6)
