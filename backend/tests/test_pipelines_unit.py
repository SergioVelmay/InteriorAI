import io
from typing import Any
from uuid import uuid4

import pytest
from PIL import Image
from pydantic import BaseModel

from app.foundry.mock import sample_from_schema
from app.pipelines.images import prepare_image
from app.pipelines.prompt_writer import (
    InputRole,
    build_context,
    history_section,
    previous_section,
    references_section,
    system_prompt,
)
from app.pipelines.prompts import load_prompt
from app.pipelines.schemas import strict_schema
from shared.models import (
    RECIPE_GROUPS,
    Asset,
    AssetKind,
    AuditReport,
    ProjectMetadata,
    RecipeElement,
    ReferenceRecipe,
    ReferenceSheet,
    RenderInpaint,
    RenderRecord,
    RenderStage,
    RenderStatus,
    StagePrompt,
    utc_now,
)

FORBIDDEN = {"$ref", "$defs", "title", "default", "minimum", "maximum", "minLength", "maxLength"}


def walk(node: Any):
    """Recorre los nodos de esquema (los nombres de campo de `properties` no son nodos)."""
    if isinstance(node, dict):
        yield node
        for key, value in node.items():
            if key == "properties":
                for sub in value.values():
                    yield from walk(sub)
            else:
                yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


class Titled(BaseModel):
    """Un campo que se llama como una palabra clave de JSON Schema."""

    title: str


@pytest.mark.parametrize("model", [ReferenceRecipe, StagePrompt, AuditReport])
def test_strict_schema_rules(model) -> None:
    schema = strict_schema(model)
    objects = [n for n in walk(schema) if "properties" in n]
    assert objects, "debe haber objetos"
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert obj["required"] == list(obj["properties"])
    for node in walk(schema):
        assert not FORBIDDEN & set(node), FORBIDDEN & set(node)


def test_strict_schema_keeps_fields_named_like_keywords() -> None:
    """Regresión: una propiedad `title` no debe confundirse con la palabra clave."""
    schema = strict_schema(Titled)
    assert "title" in schema["properties"]
    assert "title" in schema["required"]


def test_strict_schema_keeps_enums_nullables_and_descriptions() -> None:
    schema = strict_schema(RecipeElement)
    props = schema["properties"]
    assert props["dimensions_source"]["enum"] == [
        "nota_usuario", "cota_imagen", "estimada", "ninguna",
    ]  # fmt: skip
    dimensions = props["dimensions_cm"]["properties"]
    assert {"type": "null"} in dimensions["width_cm"]["anyOf"]
    assert "español" in props["label"]["description"]


@pytest.mark.parametrize("model", [ReferenceRecipe, StagePrompt, AuditReport])
def test_mock_output_for_strict_schema_validates(model) -> None:
    model.model_validate(sample_from_schema(strict_schema(model)))


def png(size: tuple[int, int], mode: str = "RGB", color: Any = "#336699") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, "PNG")
    return buffer.getvalue()


async def test_prepare_image_downscales_and_flattens_transparency() -> None:
    prepared = await prepare_image(png((3000, 1500), "RGBA", (255, 0, 0, 0)))
    assert prepared.mime_type == "image/jpeg"
    with Image.open(io.BytesIO(prepared.data)) as image:
        assert image.size == (1024, 512)
        assert image.mode == "RGB"
        assert image.getpixel((10, 10)) == (255, 255, 255)  # transparente → blanco


async def test_prepare_image_never_upscales() -> None:
    prepared = await prepare_image(png((200, 100)))
    with Image.open(io.BytesIO(prepared.data)) as image:
        assert image.size == (200, 100)


def test_prompts_are_versioned_by_content() -> None:
    for name in (
        "reference_analyst", "auditor_espacio", "prompt_bocetos", "prompt_composicion",
        "prompt_render_final", "prompt_criterios",
    ):  # fmt: skip
        prompt = load_prompt(name)
        assert prompt.text
        assert prompt.version.startswith(f"{name}@")
        assert len(prompt.version.split("@")[1]) == 12
    assert "INGLÉS" in load_prompt("prompt_bocetos").text
    assert "estimada" in load_prompt("reference_analyst").text


def test_stage_prompt_context_has_roles_selections_and_indications() -> None:
    """Paso 22: el PROMPT_ARCHITECT recibe el papel de cada imagen y solo lo marcado."""
    element = {
        "label": "Sofá JÄTTEBO",
        "detail": "",
        "dimensions_source": "estimada",
        "selected": False,
        "dimensions_cm": {"width_cm": 285, "depth_cm": None, "height_cm": None},
    }
    recipe = {"summary": "s", **{g: [element] for g in RECIPE_GROUPS}}

    def asset(name: str, selected: list[str]) -> Asset:
        sheet = ReferenceSheet.model_validate({"recipe": recipe, "selected": selected})
        return Asset(kind=AssetKind.REFERENCIA, stored_name=f"{name}.png", original_name=name,
                     mime_type="image/png", size_bytes=1, sha256="0" * 64, sheet=sheet,
                     description=f"notas de {name}")  # fmt: skip

    view, sofa = asset("vista", ["perspectiva:0"]), asset("sofa", ["objetos:0"])
    now = utc_now()
    project = ProjectMetadata(id=view.id, name="Salón", description="Luz de tarde",
                              created_at=now, updated_at=now, assets=[view, sofa])  # fmt: skip
    text = build_context(
        project, [InputRole(view, "imagen base"), InputRole(sofa, "apoyo")], [view, sofa],
        "Más cálido", "1536x1024",
    )  # fmt: skip
    assert "- Imagen 1: imagen base — «vista»" in text and "- Imagen 2: apoyo — «sofa»" in text
    assert '"imagen": 2' in text and '"Objetos y mobiliario"' in text
    # Lo marcado en `seleccion` y, de las que se envían como imagen, lo NO marcado en `ignorar`
    # (Paso 28, B-068): el modelo ve la imagen entera.
    [entry, _] = references_section([sofa, view], {view.id: 1, sofa.id: 2})
    assert list(entry["seleccion"]) == ["Objetos y mobiliario"]
    assert "Colores y paleta" in entry["ignorar"] and "Objetos y mobiliario" not in entry["ignorar"]
    assert entry["ignorar"]["Colores y paleta"] == ["Sofá JÄTTEBO"]
    [text_only] = references_section([sofa], {})
    assert "ignorar" not in text_only  # no se envía como imagen: no hace falta
    assert "lo que hay que ignorar" in text
    assert '"origen_medidas": "estimada"' in text
    assert "Luz de tarde" in text and "Más cálido" in text and "1536x1024" in text
    assert entry["resumen_analisis"] == "s"  # Paso 32: qué es la imagen y qué aporta


def test_system_prompt_adds_the_common_criteria() -> None:
    """Paso 32: cada etapa + los criterios comunes (medidas estándar, dudas, repaso final)."""
    text, version = system_prompt(RenderStage.DRAFT)
    assert text.startswith(load_prompt("prompt_bocetos").text)
    assert "medida" in text and "estándar del mercado" in text and "Repaso final" in text
    own, criteria = version.split("+")
    assert own.startswith("prompt_bocetos@") and criteria.startswith("prompt_criterios@")


def _render(stage: RenderStage, minutes: int, **extra: Any) -> RenderRecord:
    info = StagePrompt(prompt="p", interpretation=f"entendido {minutes}", open_questions=["¿x?"])
    return RenderRecord(
        id=uuid4(), stage=stage, role="FAST_DRAFT_MAKER", deployment="d",
        prompt=f"prompt {minutes}", prompt_info=info, input_asset_ids=[], batch_id=uuid4(),
        size="1536x1024", created_at=utc_now().replace(minute=minutes), **extra,
    )  # fmt: skip


def test_history_and_previous_generations_for_the_writer() -> None:
    """Paso 32: el historial de la imagen de partida (con los retoques) y las generaciones
    anteriores de la etapa (la seleccionada y la última) llegan al PROMPT_ARCHITECT."""
    draft = _render(RenderStage.DRAFT, 1, status=RenderStatus.SELECTED)
    first = _render(RenderStage.COMPOSITION, 2, parent_render_id=draft.id)
    retouch = _render(
        RenderStage.COMPOSITION, 3, parent_render_id=draft.id, status=RenderStatus.SELECTED,
        inpaint=RenderInpaint(source_render_id=first.id, instruction="frigorífico de acero",
                              mask_file="m.png", coverage=0.1),
    )  # fmt: skip
    later = _render(RenderStage.COMPOSITION, 4, parent_render_id=draft.id)
    now = utc_now()
    project = ProjectMetadata(id=uuid4(), name="Cocina", created_at=now, updated_at=now,
                              renders=[draft, first, retouch, later])  # fmt: skip

    def start(render: RenderRecord) -> list[InputRole]:
        asset = Asset(
            id=render.id, kind=AssetKind.RENDER, stored_name="r.png", original_name="r",
            mime_type="image/png", size_bytes=1, sha256="0" * 64,
        )  # fmt: skip
        return [InputRole(asset, "imagen de partida")]

    history = history_section(project, start(retouch))
    assert [h["imagen"][-8:] for h in history] == [r.id.hex[:8] for r in (draft, first, retouch)]
    assert history[-1]["retoque_pedido_por_el_usuario"] == "frigorífico de acero"
    assert history[-1]["es_la_imagen_de_partida"] is True and history[-1]["prompt"] == "prompt 3"
    assert "prompt" not in history[0] and history[0]["lo_que_se_entendio"] == "entendido 1"
    # Desde la composición seleccionada: las anteriores de la etapa son la última (no la propia).
    previous = previous_section(project, RenderStage.COMPOSITION, start(retouch))
    assert [p["imagen"][-8:] for p in previous] == [later.id.hex[:8]]
    assert previous[0]["dudas"] == ["¿x?"] and previous[0]["seleccionada"] is False
    # Bocetos (sin imagen de partida de un render): el seleccionado, sin historial.
    assert history_section(project, []) == []
    [chosen] = previous_section(project, RenderStage.DRAFT, [])
    assert chosen["seleccionada"] is True
    text = build_context(
        project, start(retouch), [], "", "1536x1024", stage=RenderStage.COMPOSITION
    )
    assert "## Historial de la imagen de partida" in text
    assert "## Generaciones anteriores de esta etapa" in text
