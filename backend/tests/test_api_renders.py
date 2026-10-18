"""Pipelines de imagen (boceto → composición → render final) con cliente mock espía."""

import io
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import image_bytes
from fastapi.testclient import TestClient
from PIL import Image

from app.foundry import ImageEditRequest, ImageResult, MockFoundryClient
from shared.roles import Role


class SpyClient(MockFoundryClient):
    def __init__(self) -> None:
        super().__init__()
        self.edits: list[tuple[Role, ImageEditRequest]] = []

    async def _edit_image(self, role: Role, request: ImageEditRequest) -> ImageResult:
        self.edits.append((role, request))
        return await super()._edit_image(role, request)


@pytest.fixture
def api(make_api: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for role, name in {
        "FAST_DRAFT": "gpt-image-2.5-flare",
        "STRUCTURAL_COMPOSER": "gpt-image-2.5-sunburst",
        "PHOTOREALISTIC_RENDERER": "FLUX.2-pro",
    }.items():
        monkeypatch.setenv(f"DEPLOYMENT_ROLE_{role}", name)
    return make_api()


@pytest.fixture
def spy(api: TestClient) -> SpyClient:
    client = SpyClient()
    api.app.state.foundry.inner = client
    return client


def new_project(api: TestClient, capture_size: tuple[int, int] = (1600, 900)) -> dict:
    pid = api.post(
        "/api/v1/projects",
        json={"name": "Salón", "space_type": "salon_cocina_comedor", "design_notes": "Sofá en L"},
    ).json()["id"]
    url = f"/api/v1/projects/{pid}"

    def upload(kind: str, content: bytes, name: str) -> str:
        response = api.post(f"{url}/assets/{kind}", files={"file": (name, content)})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    return {
        "url": url,
        "capture": upload("captura_sketchup", image_bytes(size=capture_size), "vista.png"),
        "product": upload("referencia", image_bytes(color="#556b2f"), "planificador.png"),
        "inspiration": upload("referencia", image_bytes(color="#6b8e23"), "inspiracion.jpg"),
    }


def approve_brief(api: TestClient, project: dict) -> dict:
    brief = api.post(f"{project['url']}/briefs").json()["brief"]
    api.post(f"{project['url']}/briefs/{brief['id']}/approve")
    return brief


@pytest.fixture
def project(api: TestClient, spy: SpyClient) -> dict:
    project = new_project(api)
    project["brief"] = approve_brief(api, project)
    return project


def run(api: TestClient, project: dict, stage: str, **body: object) -> dict:
    response = api.post(f"{project['url']}/renders/{stage}", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def select(api: TestClient, project: dict, render_id: str) -> dict:
    response = api.post(f"{project['url']}/renders/{render_id}/select")
    assert response.status_code == 200, response.text
    return response.json()


# --- Etapa 1: bocetos -----------------------------------------------------------------------


def test_drafts_edit_the_capture(
    api: TestClient, spy: SpyClient, project: dict, tmp_path: Path
) -> None:
    body = run(api, project, "drafts")
    renders = body["renders"]
    assert len(renders) == 2
    assert len({r["batch_id"] for r in renders}) == 1
    for render in renders:
        assert render["stage"] == "boceto"
        assert render["status"] == "generado"
        assert render["role"] == "FAST_DRAFT"
        assert render["deployment"] == "gpt-image-2.5-flare"
        assert render["size"] == "1536x1024"
        assert render["quality"] == "low"
        assert render["input_asset_ids"] == [project["capture"]]
        assert render["brief_version"] == 1
        assert render["prompt"] == project["brief"]["content"]["image_prompts"]["fast_draft"]
        assert render["request_id"] == body["request_id"]
    assert body["cost_eur"] > 0
    assert sum(r["cost_eur"] for r in renders) == pytest.approx(body["cost_eur"], abs=1e-6)

    [(role, request)] = spy.edits
    assert role is Role.FAST_DRAFT
    assert (request.n, request.size, request.quality, request.mask) == (2, "1536x1024", "low", None)
    assert len(request.images) == 1

    # imagen + JSON de trazabilidad en renders_historico/ y descarga como asset
    folder = tmp_path / "data" / project["url"].rsplit("/", 1)[1] / "renders_historico"
    render_id = renders[0]["id"]
    assert (folder / f"{render_id}.png").is_file()
    sidecar = json.loads((folder / f"{render_id}.json").read_text(encoding="utf-8"))
    assert sidecar["stage"] == "boceto" and sidecar["prompt"] == renders[0]["prompt"]
    content = api.get(f"{project['url']}/assets/{render_id}/content")
    assert content.status_code == 200
    assert content.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(content.content)) as image:
        assert image.size == (1536, 1024)


def test_generation_requires_an_approved_brief(api: TestClient, spy: SpyClient) -> None:
    project = new_project(api)
    assert api.post(f"{project['url']}/renders/drafts", json={}).status_code == 409
    brief = api.post(f"{project['url']}/briefs").json()["brief"]
    response = api.post(f"{project['url']}/renders/drafts", json={"brief_id": brief["id"]})
    assert response.status_code == 409
    assert "no está aprobado" in response.json()["detail"]
    assert spy.edits == []


def test_prompt_override_and_extra_instructions(
    api: TestClient, spy: SpyClient, project: dict
) -> None:
    body = run(
        api, project, "drafts", n=1,
        prompt_override="Olive corduroy sofa sketch", extra_instructions="Warm evening light",
    )  # fmt: skip
    expected = "Olive corduroy sofa sketch\n\nWarm evening light"
    assert body["renders"][0]["prompt"] == expected
    assert spy.edits[0][1].prompt == expected


def test_portrait_capture_defaults_to_portrait_sizes(api: TestClient, spy: SpyClient) -> None:
    project = new_project(api, capture_size=(900, 1600))
    approve_brief(api, project)
    assert run(api, project, "drafts", n=1)["renders"][0]["size"] == "1024x1536"


@pytest.mark.parametrize(
    ("stage", "size"), [("drafts", "2048x2048"), ("drafts", "grande"), ("compositions", "800x600")]
)
def test_invalid_gpt_image_sizes(
    api: TestClient, spy: SpyClient, project: dict, stage, size
) -> None:
    response = api.post(f"{project['url']}/renders/{stage}", json={"size": size})
    assert response.status_code == 422
    assert spy.edits == []


# --- Etapa 2: composición -------------------------------------------------------------------


def test_composition_with_and_without_selected_draft(
    api: TestClient, spy: SpyClient, project: dict
) -> None:
    alone = run(api, project, "compositions")["renders"][0]
    assert alone["input_asset_ids"] == [project["capture"]]
    assert alone["parent_render_id"] is None
    assert alone["quality"] == "medium"
    assert alone["role"] == "STRUCTURAL_COMPOSER"

    draft = run(api, project, "drafts", n=1)["renders"][0]
    response = api.post(f"{project['url']}/renders/compositions", json={"draft_id": draft["id"]})
    assert response.status_code == 409  # el boceto no está seleccionado

    select(api, project, draft["id"])
    composed = run(api, project, "compositions", draft_id=draft["id"])["renders"][0]
    assert composed["input_asset_ids"] == [project["capture"], draft["id"]]
    assert composed["parent_render_id"] == draft["id"]
    role, request = spy.edits[-1]
    assert role is Role.STRUCTURAL_COMPOSER
    assert len(request.images) == 2
    assert request.prompt == project["brief"]["content"]["image_prompts"]["structural_composer"]


# --- Etapa 3: render final -------------------------------------------------------------------


def selected_composition(api: TestClient, project: dict) -> dict:
    composition = run(api, project, "compositions")["renders"][0]
    select(api, project, composition["id"])
    return composition


def test_final_render_uses_composition_and_references(
    api: TestClient, spy: SpyClient, project: dict
) -> None:
    composition = run(api, project, "compositions")["renders"][0]
    response = api.post(
        f"{project['url']}/renders/final", json={"composition_id": composition["id"]}
    )
    assert response.status_code == 409  # composición no seleccionada
    select(api, project, composition["id"])

    final = run(api, project, "final", composition_id=composition["id"])["renders"][0]
    assert final["stage"] == "render_final"
    assert final["role"] == "PHOTOREALISTIC_RENDERER"
    assert final["deployment"] == "FLUX.2-pro"
    assert final["size"] == "1920x1280"
    assert final["quality"] is None
    assert final["parent_render_id"] == composition["id"]
    assert final["input_asset_ids"] == [
        composition["id"],
        project["product"],
        project["inspiration"],
    ]
    assert final["cost_eur"] > 0
    role, request = spy.edits[-1]
    assert role is Role.PHOTOREALISTIC_RENDERER
    assert request.output_format == "png"
    assert len(request.images) == 3
    content = api.get(f"{project['url']}/assets/{final['id']}/content")
    assert content.headers["content-type"] == "image/png"


def test_final_render_with_explicit_references(
    api: TestClient, spy: SpyClient, project: dict
) -> None:
    composition = selected_composition(api, project)
    final = run(
        api, project, "final", composition_id=composition["id"],
        reference_ids=[project["inspiration"]], seed=42,
    )["renders"][0]  # fmt: skip
    assert final["input_asset_ids"] == [composition["id"], project["inspiration"]]
    assert final["seed"] == 42
    response = api.post(
        f"{project['url']}/renders/final",
        json={"composition_id": composition["id"], "reference_ids": [project["capture"]]},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("size", ["1000x1000", "2048x2048", "abc"])
def test_invalid_renderer_sizes(api: TestClient, spy: SpyClient, project: dict, size: str) -> None:
    composition = selected_composition(api, project)
    response = api.post(
        f"{project['url']}/renders/final", json={"composition_id": composition["id"], "size": size}
    )
    assert response.status_code == 422


def test_wrong_stage_or_missing_render(api: TestClient, spy: SpyClient, project: dict) -> None:
    draft = run(api, project, "drafts", n=1)["renders"][0]
    select(api, project, draft["id"])
    response = api.post(f"{project['url']}/renders/final", json={"composition_id": draft["id"]})
    assert response.status_code == 422
    missing = "00000000-0000-0000-0000-000000000000"
    assert api.post(f"{project['url']}/renders/{missing}/select").status_code == 404
    response = api.post(f"{project['url']}/renders/final", json={"composition_id": missing})
    assert response.status_code == 404


# --- Decisiones del usuario, historial y borrado -----------------------------------------------


def test_select_and_discard_transitions(api: TestClient, spy: SpyClient, project: dict) -> None:
    render = run(api, project, "drafts", n=1)["renders"][0]
    url = f"{project['url']}/renders/{render['id']}"
    assert api.post(f"{url}/discard").json()["status"] == "descartado"
    selected = api.post(f"{url}/select").json()
    assert selected["status"] == "seleccionado"
    assert selected["decided_at"] is not None
    assert api.post(f"{url}/select").status_code == 409


def test_history_filter_and_order(api: TestClient, spy: SpyClient, project: dict) -> None:
    run(api, project, "drafts", n=2)
    run(api, project, "compositions")
    all_renders = api.get(f"{project['url']}/renders").json()
    assert [r["stage"] for r in all_renders] == ["composicion", "boceto", "boceto"]
    drafts = api.get(f"{project['url']}/renders", params={"stage": "boceto"}).json()
    assert len(drafts) == 2


def test_deleting_a_render_removes_its_record(
    api: TestClient, spy: SpyClient, project: dict, tmp_path: Path
) -> None:
    render = run(api, project, "drafts", n=1)["renders"][0]
    assert api.delete(f"{project['url']}/assets/{render['id']}").status_code == 204
    assert api.get(f"{project['url']}/renders").json() == []
    project_id = project["url"].rsplit("/", 1)[1]
    trash = tmp_path / "data" / ".papelera" / project_id
    assert any(p.name.endswith(f"{render['id']}.json") for p in trash.iterdir())


def test_render_calls_are_in_project_telemetry(
    api: TestClient, spy: SpyClient, project: dict
) -> None:
    run(api, project, "drafts")
    selected_composition(api, project)
    by_role = {g["key"]: g for g in api.get(f"{project['url']}/costs").json()["by_role"]}
    assert by_role["FAST_DRAFT"]["images_out"] == 2
    assert by_role["STRUCTURAL_COMPOSER"]["calls"] == 1
