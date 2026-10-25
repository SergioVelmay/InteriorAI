"""Pipelines de imagen (boceto → composición → render final) con cliente mock espía."""

import io
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import image_bytes, mark_active, mark_legacy
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
        json={"name": "Salón", "description": "Sofá en L"},
    ).json()["id"]
    url = f"/api/v1/projects/{pid}"

    def upload(kind: str, content: bytes, name: str) -> str:
        response = api.post(f"{url}/assets/{kind}", files={"file": (name, content)})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    project = {
        "url": url,
        "capture": upload("referencia", image_bytes(size=capture_size), "vista.png"),
        "product": upload("referencia", image_bytes(color="#556b2f"), "planificador.png"),
        "inspiration": upload("referencia", image_bytes(color="#6b8e23"), "inspiracion.jpg"),
    }
    mark_legacy(api, pid, {project["capture"]: "captura_sketchup"})  # migrada de la v1 (B-028)
    # Fichas guardadas (B-030): la vista aporta la perspectiva; las demás, objetos y color.
    mark_active(api, pid, {project["capture"]: ["perspectiva"],
                           project["product"]: ["objetos"],
                           project["inspiration"]: ["colores"]})  # fmt: skip
    return project


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


def test_drafts_from_active_references_with_an_automatic_prompt(
    api: TestClient, spy: SpyClient, project: dict, tmp_path: Path
) -> None:
    """B-036 y Paso 22: la vista con perspectiva es la base; las demás activas, apoyos; el
    PROMPT_ENGINEER escribe el prompt de esta generación (sin brief)."""
    body = run(api, project, "drafts", n=2, extra_instructions="Luz de tarde")
    renders = body["renders"]
    assert len(renders) == 2
    assert len({r["batch_id"] for r in renders}) == 1
    for render in renders:
        assert render["stage"] == "boceto"
        assert render["status"] == "generado"
        assert render["role"] == "FAST_DRAFT"
        assert render["deployment"] == "gpt-image-2.5-flare"
        assert render["size"] == "1536x1024"
        assert render["quality"] == "medium"  # por defecto (B-040)
        assert render["input_asset_ids"] == [
            project["capture"], project["product"], project["inspiration"],
        ]  # fmt: skip
        assert render["brief_id"] is None and render["brief_version"] is None
        assert render["prompt"] == render["prompt_info"]["prompt"] == "mock"
        assert render["prompt_info"]["interpretation"] == "mock"
        assert render["prompt_version"].startswith("prompt_bocetos@")
        assert render["request_id"] == body["request_id"]
    assert body["cost_eur"] > 0
    # Cada imagen redondea su parte a 6 decimales: la suma puede desviarse en ~1e-6
    assert sum(r["cost_eur"] for r in renders) == pytest.approx(body["cost_eur"], abs=2e-6)

    [(role, request)] = spy.edits
    assert role is Role.FAST_DRAFT
    assert (request.n, request.size, request.quality, request.mask) == (
        2, "1536x1024", "medium", None,
    )  # fmt: skip
    assert len(request.images) == 3

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


def test_drafts_require_an_active_reference(api: TestClient, spy: SpyClient) -> None:
    project = new_project(api)
    pid = project["url"].rsplit("/", 1)[1]
    mark_active(api, pid, {project[k]: [] for k in ("capture", "product", "inspiration")})
    response = api.post(f"{project['url']}/renders/drafts", json={})
    assert response.status_code == 422
    assert "Activa al menos una referencia" in response.json()["detail"]
    assert spy.edits == []


def test_drafts_without_perspective_compose_freely(api: TestClient, spy: SpyClient) -> None:
    """Sin imagen base obligatoria: sin perspectiva marcada, todas las activas son apoyos."""
    project = new_project(api)
    pid = project["url"].rsplit("/", 1)[1]
    mark_active(api, pid, {project["capture"]: []})  # la vista, descartada
    render = run(api, project, "drafts", n=1)["renders"][0]
    assert render["input_asset_ids"] == [project["product"], project["inspiration"]]


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


def test_draft_format_is_chosen_by_the_user(api: TestClient, spy: SpyClient) -> None:
    """B-040: 3:2 por defecto, también con una vista vertical; el usuario elige el formato."""
    project = new_project(api, capture_size=(900, 1600))
    assert run(api, project, "drafts", n=1)["renders"][0]["size"] == "1536x1024"
    portrait = run(api, project, "drafts", n=1, size="1024x1536")["renders"][0]
    assert portrait["size"] == "1024x1536"


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
    assert final["size"] == "1920x1080"  # proporción exacta de la captura (16:9)
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
    assert request.size == "1920x1088"  # el renderizador trabaja en múltiplos de 16 px
    content = api.get(f"{project['url']}/assets/{final['id']}/content")
    assert content.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(content.content)) as image:
        assert image.size == (1920, 1080)  # recortado al centro, sin escalar


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
    assert response.status_code == 201  # elegida por el usuario: cualquier referencia activa
    pid = project["url"].rsplit("/", 1)[1]
    mark_active(api, pid, {project["inspiration"]: []})  # descartada
    response = api.post(
        f"{project['url']}/renders/final",
        json={"composition_id": composition["id"], "reference_ids": [project["inspiration"]]},
    )
    assert response.status_code == 422  # una referencia descartada no se usa


@pytest.mark.parametrize("size", ["200x200", "2048x2048", "abc"])
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


def test_select_transition(api: TestClient, spy: SpyClient, project: dict) -> None:
    render = run(api, project, "drafts", n=1)["renders"][0]
    url = f"{project['url']}/renders/{render['id']}"
    selected = api.post(f"{url}/select").json()
    assert selected["status"] == "seleccionado"
    assert selected["decided_at"] is not None
    assert api.post(f"{url}/select").status_code == 409


def test_one_selected_render_per_stage(api: TestClient, spy: SpyClient, project: dict) -> None:
    first, second = run(api, project, "drafts", n=2)["renders"]
    composition = run(api, project, "compositions")["renders"][0]
    for render in (first, composition, second):
        select(api, project, render["id"])
    statuses = {r["id"]: r["status"] for r in api.get(f"{project['url']}/renders").json()}
    assert statuses == {
        first["id"]: "generado",  # la etapa admite una sola imagen seleccionada (B-043)
        second["id"]: "seleccionado",
        composition["id"]: "seleccionado",  # otras etapas no cambian
    }


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
    assert by_role["FAST_DRAFT"]["images_out"] == 4  # 4 variantes por defecto (B-043)
    assert by_role["STRUCTURAL_COMPOSER"]["calls"] == 1


def test_final_size_follows_the_capture(api: TestClient, spy: SpyClient) -> None:
    project = new_project(api, capture_size=(900, 1200))  # vertical 3:4
    approve_brief(api, project)
    composition = selected_composition(api, project)
    final = run(api, project, "final", composition_id=composition["id"])["renders"][0]
    assert final["size"] == "1440x1920"
    explicit = run(api, project, "final", composition_id=composition["id"], size="1280x1920")
    assert explicit["renders"][0]["size"] == "1280x1920"


# --- Retoque de una zona (inpainting) ------------------------------------------------------


def zone_mask(size: tuple[int, int], box: tuple[int, int, int, int]) -> bytes:
    """Máscara como la del editor: transparente salvo la zona pintada (opaca)."""
    mask = Image.new("RGBA", size, (0, 0, 0, 0))
    if box[2] > box[0] and box[3] > box[1]:
        mask.paste((255, 0, 0, 255), box)
    buffer = io.BytesIO()
    mask.save(buffer, "PNG")
    return buffer.getvalue()


def inpaint(api: TestClient, project: dict, render_id: str, mask: bytes, **form: str):
    return api.post(
        f"{project['url']}/renders/{render_id}/inpaint",
        files={"mask": ("mascara.png", mask, "image/png")},
        data={"instruction": "Cojines en mostaza", **form},
    )


def pixels(api: TestClient, project: dict, render_id: str) -> Image.Image:
    content = api.get(f"{project['url']}/assets/{render_id}/content").content
    return Image.open(io.BytesIO(content)).convert("RGB")


def test_inpaint_composition_uses_the_native_mask(
    api: TestClient, spy: SpyClient, project: dict, tmp_path: Path
) -> None:
    composition = run(api, project, "compositions")["renders"][0]
    # Máscara a mitad de resolución (misma proporción): se escala a la imagen.
    response = inpaint(api, project, composition["id"], zone_mask((768, 512), (100, 100, 300, 300)))
    assert response.status_code == 201, response.text
    body = response.json()
    [retouch] = body["renders"]
    assert body["cost_eur"] > 0
    assert retouch["stage"] == "composicion" and retouch["status"] == "generado"
    assert retouch["role"] == "STRUCTURAL_COMPOSER" and retouch["quality"] == "medium"
    assert retouch["input_asset_ids"] == [composition["id"]]
    assert retouch["size"] == "1536x1024"
    info = retouch["inpaint"]
    assert info["source_render_id"] == composition["id"]
    assert info["method"] == "mascara" and info["instruction"] == "Cojines en mostaza"
    assert info["coverage"] == pytest.approx(200 * 200 / (768 * 512), abs=1e-3)

    role, request = spy.edits[-1]
    assert role is Role.STRUCTURAL_COMPOSER and request.mask is not None
    assert "Cojines en mostaza" in request.prompt
    with Image.open(io.BytesIO(request.mask.data)) as mask:  # transparente = editar
        assert mask.getpixel((400, 400))[3] == 0 and mask.getpixel((10, 10))[3] == 255

    # Sin recomponer (B-038): la imagen es la que devuelve el modelo, completa.
    original, edited = pixels(api, project, composition["id"]), pixels(api, project, retouch["id"])
    assert edited.size == original.size == (1536, 1024)
    assert edited.tobytes() != original.tobytes()

    assert "fit entirely inside" in request.prompt and "% of the width" in request.prompt

    # Solo se guarda la máscara: sin salida en bruto ni guía.
    folder = tmp_path / "data" / project["url"].rsplit("/", 1)[1] / "renders_historico"
    assert (folder / info["mask_file"]).is_file()
    assert info["raw_file"] is None and info["guide_file"] is None and info["feather_px"] is None
    url = f"{project['url']}/renders/{retouch['id']}/inpaint"
    mask = api.get(f"{url}/mascara")
    assert mask.status_code == 200 and mask.headers["content-type"] == "image/png"
    assert api.get(f"{url}/bruto").status_code == 422  # solo la máscara (B-038)
    assert api.get(f"{url}/guia").status_code == 422
    source_mask = f"{project['url']}/renders/{composition['id']}/inpaint/mascara"
    assert api.get(source_mask).status_code == 404  # la original no es un retoque


def test_final_render_cannot_be_retouched(api: TestClient, spy: SpyClient, project: dict) -> None:
    composition = selected_composition(api, project)
    final = run(api, project, "final", composition_id=composition["id"])["renders"][0]
    calls = len(spy.edits)
    response = inpaint(api, project, final["id"], zone_mask((1920, 1080), (800, 400, 1200, 800)))
    assert response.status_code == 422  # solo composiciones (B-038)
    assert "composiciones" in response.json()["detail"]
    assert len(spy.edits) == calls
    assert api.post(f"{project['url']}/renders/{final['id']}/raw").status_code in {404, 405}


def test_inpaint_validation(api: TestClient, spy: SpyClient, project: dict) -> None:
    draft = run(api, project, "drafts", n=1)["renders"][0]
    composition = run(api, project, "compositions")["renders"][0]
    box = (10, 10, 50, 50)
    assert inpaint(api, project, draft["id"], zone_mask((1536, 1024), box)).status_code == 422
    empty = zone_mask((1536, 1024), (0, 0, 0, 0))
    assert inpaint(api, project, composition["id"], empty).status_code == 422
    full = zone_mask((1536, 1024), (0, 0, 1536, 1024))
    assert inpaint(api, project, composition["id"], full).status_code == 422
    square = zone_mask((1024, 1024), box)  # otra proporción
    response = inpaint(api, project, composition["id"], square)
    assert response.status_code == 422 and "proporción" in response.json()["detail"]
    not_image = api.post(
        f"{project['url']}/renders/{composition['id']}/inpaint",
        files={"mask": ("mascara.png", b"no soy una imagen", "image/png")},
        data={"instruction": "x"},
    )
    assert not_image.status_code == 415
    missing = "00000000-0000-0000-0000-000000000000"
    assert inpaint(api, project, missing, zone_mask((1536, 1024), box)).status_code == 404
    assert len(spy.edits) == 2  # ninguna petición inválida llega al modelo


def test_deleting_a_retouch_moves_its_files_to_the_trash(
    api: TestClient, spy: SpyClient, project: dict, tmp_path: Path
) -> None:
    composition = run(api, project, "compositions")["renders"][0]
    retouch = inpaint(
        api, project, composition["id"], zone_mask((1536, 1024), (100, 100, 300, 300))
    ).json()["renders"][0]

    # Borrar el retoque se lleva también su máscara a la papelera.
    assert api.delete(f"{project['url']}/assets/{retouch['id']}").status_code == 204
    trash = tmp_path / "data" / ".papelera" / project["url"].rsplit("/", 1)[1]
    names = [p.name for p in trash.iterdir()]
    assert any(n.endswith(retouch["inpaint"]["mask_file"]) for n in names)


def test_render_chain_cost(api: TestClient, spy: SpyClient, project: dict) -> None:
    drafts = run(api, project, "drafts", n=2)["renders"]
    select(api, project, drafts[0]["id"])
    composition = run(api, project, "compositions", draft_id=drafts[0]["id"])["renders"][0]
    select(api, project, composition["id"])
    final = run(api, project, "final", composition_id=composition["id"])["renders"][0]
    other = run(api, project, "drafts", n=1)  # otra rama: no cuenta

    cost = api.get(f"{project['url']}/renders/{final['id']}/cost").json()
    assert cost["renders"] == 3 and cost["briefs"] == 0  # sin brief desde el Paso 22
    assert cost["totals"]["calls"] == 0  # en simulación todo va aparte
    # 3 prompts automáticos + lote de 2 bocetos + composición + final
    assert cost["simulated_calls"] == 6
    records = api.get(f"{project['url']}/costs").json()["records"]
    expected = sum(r["cost_eur"] or 0 for r in records if r["request_id"] != other["request_id"])
    assert cost["simulated_cost_eur"] == pytest.approx(expected, abs=1e-6)
    missing = "00000000-0000-0000-0000-000000000000"
    assert api.get(f"{project['url']}/renders/{missing}/cost").status_code == 404


def test_render_chain_cost_includes_reference_indexing(api: TestClient, spy: SpyClient) -> None:
    """B-022: las recetas de las referencias que usa el brief cuentan en la cadena."""
    project = new_project(api)
    indexed = api.post(f"{project['url']}/references/index", json={"force": True})
    assert indexed.status_code == 200, indexed.text
    assert len(indexed.json()["indexed"]) == 3
    assets = api.get(f"{project['url']}/assets", params={"kind": "referencia"}).json()
    request_id = indexed.headers["x-request-id"]
    assert all(a["sheet"]["request_id"] == request_id for a in assets)
    brief = approve_brief(api, project)
    assert len(brief["reference_asset_ids"]) == 3  # las tres activas
    composition = run(api, project, "compositions")["renders"][0]

    cost = api.get(f"{project['url']}/renders/{composition['id']}/cost").json()
    assert cost["references"] == 3 and cost["briefs"] == 1
    assert cost["simulated_calls"] == 5  # 3 recetas + brief + composición
