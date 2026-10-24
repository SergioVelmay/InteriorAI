import base64
from collections.abc import Callable
from uuid import uuid4

import pytest
from conftest import image_bytes
from fastapi.testclient import TestClient

PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"


@pytest.fixture
def project_url(api: TestClient) -> str:
    response = api.post("/api/v1/projects", json={"name": "Dormitorio"})
    return f"/api/v1/projects/{response.json()['id']}"


def new_project_url(api: TestClient) -> str:
    response = api.post("/api/v1/projects", json={"name": "x"})
    return f"/api/v1/projects/{response.json()['id']}"


def upload(
    api: TestClient, url: str, kind: str, content: bytes, name: str = "plano.png", **params: str
):
    return api.post(f"{url}/assets/{kind}", files={"file": (name, content)}, params=params)


def upload_b64(api: TestClient, url: str, kind: str, data: str, name: str = "ref.png"):
    return api.post(f"{url}/assets/{kind}/base64", json={"filename": name, "data_base64": data})


# --- Subida correcta -----------------------------------------------------------------------


def test_multipart_upload_detects_type_and_dimensions(api: TestClient, project_url: str) -> None:
    response = upload(
        api, project_url, "referencia", image_bytes(size=(320, 200)), "Plano Salón.png"
    )
    assert response.status_code == 201, response.text
    asset = response.json()
    assert asset["kind"] == "referencia"
    assert asset["legacy_kind"] is None
    assert asset["mime_type"] == "image/png"
    assert (asset["width_px"], asset["height_px"]) == (320, 200)
    assert asset["original_name"] == "Plano Salón.png"
    assert asset["stored_name"] == f"{asset['id']}.png"
    assert response.headers["location"].endswith(f"/assets/{asset['id']}")


def test_type_comes_from_content_not_from_name(api: TestClient, project_url: str) -> None:
    asset = upload(api, project_url, "referencia", image_bytes("JPEG"), "foto.png").json()
    assert asset["mime_type"] == "image/jpeg"


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_image_formats_accepted(api: TestClient, project_url: str, fmt: str) -> None:
    assert upload(api, project_url, "referencia", image_bytes(fmt)).status_code == 201


def test_pdf_is_rejected(api: TestClient, project_url: str) -> None:
    """Solo imágenes (Paso 12): un PDF nunca llegaba a los modelos."""
    rejected = upload(api, project_url, "referencia", PDF, "documento.pdf")
    assert rejected.status_code == 415
    assert "PNG" in rejected.json()["detail"]


def test_base64_and_data_url_uploads(api: TestClient, project_url: str) -> None:
    raw = base64.b64encode(image_bytes(color="#22c55e")).decode()
    assert upload_b64(api, project_url, "referencia", raw).status_code == 201
    data_url = "data:image/png;base64," + base64.b64encode(image_bytes(color="#ef4444")).decode()
    assert upload_b64(api, project_url, "referencia", data_url).status_code == 201
    assert len(api.get(f"{project_url}/assets").json()) == 2


# --- Rechazos --------------------------------------------------------------------------


def test_render_cannot_be_uploaded(api: TestClient, project_url: str) -> None:
    assert upload(api, project_url, "render", image_bytes()).status_code == 422
    assert upload_b64(api, project_url, "render", "aGVsbG8=").status_code == 422


@pytest.mark.parametrize("kind", ["plano", "captura_sketchup"])
def test_v1_kinds_cannot_be_uploaded(api: TestClient, project_url: str, kind: str) -> None:
    assert upload(api, project_url, kind, image_bytes()).status_code == 422  # B-028


def test_text_disguised_as_png_is_rejected(api: TestClient, project_url: str) -> None:
    response = upload(api, project_url, "referencia", b"no soy una imagen", "plano.png")
    assert response.status_code == 415


def test_corrupt_image_is_rejected(api: TestClient, project_url: str) -> None:
    truncated = image_bytes(size=(400, 400), mode="RGB", color="#123456")[:-60]
    response = upload(api, project_url, "referencia", truncated)
    assert response.status_code == 415
    assert "dañada" in response.json()["detail"]


def test_decompression_bomb_is_rejected(api: TestClient, project_url: str) -> None:
    bomb = image_bytes(size=(10_000, 10_000), mode="1", color=0)  # 100 MP en pocos KB
    assert len(bomb) < 100_000
    response = upload(api, project_url, "referencia", bomb)
    assert response.status_code == 413
    assert "píxeles" in response.json()["detail"]


@pytest.mark.parametrize("payload", ["@@no-base64@@", "", "   "])
def test_invalid_base64(api: TestClient, project_url: str, payload: str) -> None:
    assert upload_b64(api, project_url, "referencia", payload).status_code == 422


def test_empty_file_is_rejected(api: TestClient, project_url: str) -> None:
    assert upload(api, project_url, "referencia", b"").status_code == 422


def test_upload_to_missing_project(api: TestClient) -> None:
    response = upload(api, f"/api/v1/projects/{uuid4()}", "referencia", image_bytes())
    assert response.status_code == 404


# --- Duplicados --------------------------------------------------------------------------


def test_duplicate_returns_409_unless_allowed(api: TestClient, project_url: str) -> None:
    content = image_bytes(color="#f59e0b")
    first = upload(api, project_url, "referencia", content, "a.png").json()

    duplicate = upload(api, project_url, "referencia", content, "b.png")
    assert duplicate.status_code == 409
    assert duplicate.json()["existing_asset_id"] == first["id"]
    assert "a.png" in duplicate.json()["detail"]

    forced = upload(api, project_url, "referencia", content, "b.png", allow_duplicate="true")
    assert forced.status_code == 201


# --- Tamaño ------------------------------------------------------------------------------


def test_file_over_limit_is_rejected(make_api: Callable[..., TestClient]) -> None:
    api = make_api(max_upload_mb=1)
    url = new_project_url(api)
    response = upload(api, url, "referencia", b"\x89PNG\r\n\x1a\n" + b"0" * (1024 * 1024 + 1))
    assert response.status_code == 413
    assert "1 MB" in response.json()["detail"]


def test_base64_over_limit_is_rejected_before_decoding(
    make_api: Callable[..., TestClient],
) -> None:
    api = make_api(max_upload_mb=1)
    url = new_project_url(api)
    big = base64.b64encode(b"0" * (1024 * 1024 + 10)).decode()
    assert upload_b64(api, url, "referencia", big).status_code == 413


def test_body_over_global_limit_is_rejected_by_middleware(
    make_api: Callable[..., TestClient],
) -> None:
    api = make_api(max_upload_mb=1)  # límite de cuerpo ~2.33 MB
    response = api.post("/api/v1/projects", content=b"0" * (3 * 1024 * 1024))
    assert response.status_code == 413


def test_chunked_body_over_limit_is_rejected(make_api: Callable[..., TestClient]) -> None:
    api = make_api(max_upload_mb=1)

    def chunks():
        for _ in range(30):
            yield b"0" * (128 * 1024)  # 3.75 MB sin Content-Length

    response = api.post("/api/v1/projects", content=chunks())
    assert response.status_code == 413


# --- Consulta, descarga y borrado ----------------------------------------------------------


def test_list_filter_get_and_download(api: TestClient, project_url: str) -> None:
    content = image_bytes(size=(10, 10))
    plano = upload(api, project_url, "referencia", content, "Cocina ñ.png").json()
    upload(api, project_url, "referencia", image_bytes(color="#000000"))

    assert len(api.get(f"{project_url}/assets").json()) == 2
    assert len(api.get(f"{project_url}/assets", params={"kind": "referencia"}).json()) == 2
    assert api.get(f"{project_url}/assets", params={"kind": "render"}).json() == []
    assert api.get(f"{project_url}/assets/{plano['id']}").json()["sha256"] == plano["sha256"]

    download = api.get(f"{project_url}/assets/{plano['id']}/content")
    assert download.status_code == 200
    assert download.content == content
    assert download.headers["content-type"] == "image/png"
    assert download.headers["x-content-type-options"] == "nosniff"
    assert "inline" in download.headers["content-disposition"]
    assert "filename*=utf-8''Cocina%20%C3%B1.png" in download.headers["content-disposition"]


def test_malicious_filename_cannot_inject_headers(api: TestClient, project_url: str) -> None:
    raw = base64.b64encode(image_bytes()).decode()
    asset = upload_b64(api, project_url, "referencia", raw, 'x"\r\nX-Evil: 1\r\n.png').json()
    assert "\r" not in asset["original_name"]
    assert '"' not in asset["original_name"]
    download = api.get(f"{project_url}/assets/{asset['id']}/content")
    assert download.status_code == 200
    assert "x-evil" not in download.headers


def test_delete_asset(api: TestClient, project_url: str) -> None:
    asset = upload(api, project_url, "referencia", image_bytes()).json()
    assert api.delete(f"{project_url}/assets/{asset['id']}").status_code == 204
    assert api.get(f"{project_url}/assets/{asset['id']}").status_code == 404
    assert api.get(f"{project_url}/assets/{asset['id']}/content").status_code == 404
    assert api.delete(f"{project_url}/assets/{asset['id']}").status_code == 404
