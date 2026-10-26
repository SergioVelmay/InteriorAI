import io
from typing import Any

import pytest
from PIL import Image

from app.foundry.mock import sample_from_schema
from app.pipelines.images import prepare_image
from app.pipelines.prompt_writer import InputRole, build_context, references_section
from app.pipelines.prompts import load_prompt
from app.pipelines.schemas import strict_schema
from shared.models import (
    RECIPE_GROUPS,
    Asset,
    AssetKind,
    DesignBriefContent,
    ProjectMetadata,
    ReferenceAnalysis,
    ReferenceRecipe,
    ReferenceSheet,
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


@pytest.mark.parametrize(
    "model", [ReferenceAnalysis, DesignBriefContent, ReferenceRecipe, StagePrompt]
)
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
    """Regresión: la propiedad `title` del brief no debe confundirse con la palabra clave."""
    schema = strict_schema(DesignBriefContent)
    assert "title" in schema["properties"]
    assert "title" in schema["required"]


def test_strict_schema_keeps_enums_nullables_and_descriptions() -> None:
    schema = strict_schema(ReferenceAnalysis)
    props = schema["properties"]
    assert "sofa" in props["category"]["enum"]
    assert {"type": "null"} in props["brand"]["anyOf"]
    assert props["dimensions_source"]["enum"] == ["nota_usuario", "imagen", "desconocido"]
    assert "español" in props["summary"]["description"]


@pytest.mark.parametrize(
    "model", [ReferenceAnalysis, DesignBriefContent, ReferenceRecipe, StagePrompt]
)
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
        "reference_analyst", "brief_v1", "prompt_bocetos", "prompt_composicion",
        "prompt_render_final",
    ):  # fmt: skip
        prompt = load_prompt(name)
        assert prompt.text
        assert prompt.version.startswith(f"{name}@")
        assert len(prompt.version.split("@")[1]) == 12
    assert "INGLÉS" in load_prompt("brief_v1").text
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
