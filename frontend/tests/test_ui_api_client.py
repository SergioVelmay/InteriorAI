import json
from uuid import uuid4

import httpx
import pytest

from shared.models import ProjectCreate, ProjectUpdate, utc_now
from ui.api_client import ApiError, BackendClient

BACKEND = "http://backend.test"


def project_json(name: str = "Salón") -> dict:
    now = utc_now().isoformat()
    return {
        "schema_version": 2, "id": str(uuid4()), "name": name,
        "description": "", "created_at": now, "updated_at": now, "assets": [], "briefs": [],
        "renders": [],
    }  # fmt: skip


def client_for(handler) -> tuple[BackendClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return BackendClient(BACKEND, transport=httpx.MockTransport(recording)), seen


async def test_project_crud_requests() -> None:
    body = project_json()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path == "/api/v1/projects" and request.method == "GET":
            return httpx.Response(
                200,
                json=[{k: body[k] for k in ("id", "name", "created_at", "updated_at")}],
            )
        return httpx.Response(200, json=body)

    client, seen = client_for(handler)
    assert (await client.list_projects())[0].name == "Salón"
    assert (await client.get_project(body["id"])).id.hex == body["id"].replace("-", "")
    await client.create_project(ProjectCreate(name="Salón"))
    await client.update_project(body["id"], ProjectUpdate(name="Nuevo"))
    await client.delete_project(body["id"])

    assert [(r.method, r.url.path) for r in seen] == [
        ("GET", "/api/v1/projects"),
        ("GET", f"/api/v1/projects/{body['id']}"),
        ("POST", "/api/v1/projects"),
        ("PATCH", f"/api/v1/projects/{body['id']}"),
        ("DELETE", f"/api/v1/projects/{body['id']}"),
    ]
    assert json.loads(seen[3].content) == {"name": "Nuevo"}  # solo los campos enviados
    assert all(r.headers["x-request-id"].startswith("ui-") for r in seen)
    assert len({r.headers["x-request-id"] for r in seen}) == len(seen)


async def test_costs_and_health_and_catalog() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "version": "0.1.0",
                    "mode": "azure",
                    "data_dir_writable": True,
                },
            )
        assert request.url.params["limit"] == "0"
        return httpx.Response(200, json={"totals": {"cost_eur": 0.5}})

    client, _ = client_for(handler)
    assert (await client.health()).mode == "azure"
    assert (await client.project_costs(uuid4()))["totals"]["cost_eur"] == 0.5


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (404, {"detail": "Proyecto no encontrado"}, "Proyecto no encontrado"),
        (
            422,
            {"detail": [{"msg": "campo obligatorio"}, {"msg": "otro"}]},
            "campo obligatorio; otro",
        ),
        (500, None, "Error 500 del backend"),
    ],
)
async def test_api_errors_carry_spanish_detail(status, payload, expected) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if payload is None:
            return httpx.Response(status, text="boom")
        return httpx.Response(status, json=payload)

    client, _ = client_for(handler)
    with pytest.raises(ApiError) as exc:
        await client.get_project(uuid4())
    assert exc.value.status_code == status
    assert exc.value.detail == expected


async def test_unreachable_backend() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    client, _ = client_for(handler)
    with pytest.raises(ApiError) as exc:
        await client.health()
    assert exc.value.status_code is None
    assert "No se puede conectar" in exc.value.detail
