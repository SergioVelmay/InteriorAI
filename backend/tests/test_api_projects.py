from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/projects"


def create(api: TestClient, **overrides: object) -> dict:
    body = {"name": "Salón principal", "space_type": "salon_cocina_comedor"} | overrides
    response = api.post(BASE, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_catalog_space_types(api: TestClient) -> None:
    types = api.get("/api/v1/space-types").json()
    assert {"value": "dormitorio", "label": "Dormitorio"} in types
    assert len(types) == 9


def test_catalog_asset_kinds_marks_render_as_not_uploadable(api: TestClient) -> None:
    kinds = {k["value"]: k for k in api.get("/api/v1/asset-kinds").json()}
    assert kinds["render"]["uploadable"] is False
    assert kinds["plano"]["uploadable"] is True
    assert "application/pdf" in kinds["plano"]["accepted_mime_types"]
    assert "application/pdf" not in kinds["referencia"]["accepted_mime_types"]


def test_create_returns_201_with_location(api: TestClient) -> None:
    response = api.post(BASE, json={"name": "Estudio", "space_type": "estudio"})
    assert response.status_code == 201
    project = response.json()
    assert response.headers["location"].endswith(f"{BASE}/{project['id']}")
    assert project["assets"] == []
    assert project["schema_version"] == 1


def test_full_project_lifecycle(api: TestClient) -> None:
    project = create(api, design_notes="Luz natural", dimensions={"width_m": 4, "length_m": 6.5})
    pid = project["id"]

    assert [p["id"] for p in api.get(BASE).json()] == [pid]
    assert api.get(f"{BASE}/{pid}").json()["dimensions"]["length_m"] == 6.5

    patched = api.patch(f"{BASE}/{pid}", json={"name": "Salón renovado"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Salón renovado"
    assert patched.json()["design_notes"] == "Luz natural"

    assert api.delete(f"{BASE}/{pid}").status_code == 204
    assert api.get(f"{BASE}/{pid}").status_code == 404
    assert api.get(BASE).json() == []


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "space_type": "salon"},
        {"name": "x", "space_type": "garaje"},
        {"name": "x"},
        {"name": "x", "space_type": "salon", "is_admin": True},
        {"name": "x", "space_type": "salon", "dimensions": {"width_m": -1, "length_m": 2}},
    ],
)
def test_create_validation_errors(api: TestClient, body: dict) -> None:
    assert api.post(BASE, json=body).status_code == 422


def test_patch_cannot_null_required_fields(api: TestClient) -> None:
    pid = create(api)["id"]
    assert api.patch(f"{BASE}/{pid}", json={"name": None}).status_code == 422


def test_not_found_and_invalid_ids(api: TestClient) -> None:
    missing = uuid4()
    assert api.get(f"{BASE}/{missing}").json() == {"detail": "Proyecto no encontrado"}
    assert api.get(f"{BASE}/{missing}").status_code == 404
    assert api.patch(f"{BASE}/{missing}", json={"name": "x"}).status_code == 404
    assert api.delete(f"{BASE}/{missing}").status_code == 404
    assert api.get(f"{BASE}/no-es-un-uuid").status_code == 422
    assert api.get(f"{BASE}/..%2F..%2Fetc").status_code in {404, 422}


def test_corrupt_metadata_returns_generic_500(api: TestClient, tmp_path) -> None:
    pid = create(api)["id"]
    (tmp_path / "data" / pid / "metadatos.json").write_text("{roto", encoding="utf-8")
    response = api.get(f"{BASE}/{pid}")
    assert response.status_code == 500
    assert "dañados" in response.json()["detail"]
    assert "roto" not in response.text
