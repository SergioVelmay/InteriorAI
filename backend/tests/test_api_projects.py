from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/projects"


def create(api: TestClient, **overrides: object) -> dict:
    body = {"name": "Salón principal"} | overrides
    response = api.post(BASE, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_space_types_catalog_was_removed(api: TestClient) -> None:
    assert api.get("/api/v1/space-types").status_code == 404  # B-026


def test_catalog_asset_kinds_marks_render_as_not_uploadable(api: TestClient) -> None:
    kinds = {k["value"]: k for k in api.get("/api/v1/asset-kinds").json()}
    assert kinds["render"]["uploadable"] is False
    assert kinds["plano"]["uploadable"] is True
    images = ["image/jpeg", "image/png", "image/webp"]
    assert kinds["plano"]["accepted_mime_types"] == images  # solo imágenes (Paso 12)
    assert kinds["referencia"]["accepted_mime_types"] == images


def test_create_returns_201_with_location(api: TestClient) -> None:
    response = api.post(BASE, json={"name": "Estudio"})
    assert response.status_code == 201
    project = response.json()
    assert response.headers["location"].endswith(f"{BASE}/{project['id']}")
    assert project["assets"] == []
    assert project["schema_version"] == 2


def test_full_project_lifecycle(api: TestClient) -> None:
    project = create(api, description="Luz natural; 4 x 6,5 m")
    pid = project["id"]

    assert [p["id"] for p in api.get(BASE).json()] == [pid]
    assert api.get(f"{BASE}/{pid}").json()["description"] == "Luz natural; 4 x 6,5 m"

    patched = api.patch(f"{BASE}/{pid}", json={"name": "Salón renovado"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Salón renovado"
    assert patched.json()["description"] == "Luz natural; 4 x 6,5 m"

    assert api.delete(f"{BASE}/{pid}").status_code == 204
    assert api.get(f"{BASE}/{pid}").status_code == 404
    assert api.get(BASE).json() == []


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "x", "is_admin": True},
        {"name": "x", "space_type": "salon"},  # campos eliminados en la v2 (B-026)
        {"name": "x", "design_notes": "Luz"},
        {"name": "x", "description": "x" * 25_001},
    ],
)
def test_create_validation_errors(api: TestClient, body: dict) -> None:
    assert api.post(BASE, json=body).status_code == 422


def test_patch_cannot_null_required_fields(api: TestClient) -> None:
    pid = create(api)["id"]
    assert api.patch(f"{BASE}/{pid}", json={"name": None}).status_code == 422
    assert api.patch(f"{BASE}/{pid}", json={"description": None}).status_code == 422


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
