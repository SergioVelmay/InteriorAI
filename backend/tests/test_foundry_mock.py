import io

import pytest
from PIL import Image

from app.foundry import (
    FoundryUnsupportedError,
    ImageEditRequest,
    ImageRequest,
    InputImage,
    MockFoundryClient,
    TextRequest,
    create_foundry_client,
)
from app.foundry.mock import sample_from_schema
from shared import Settings
from shared.roles import Role

SCHEMA = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"},
        "puntuacion": {"type": "integer", "minimum": 1},
        "aprobado": {"type": "boolean"},
        "estilo": {"type": "string", "enum": ["nordico", "industrial"]},
        "elementos": {"type": "array", "items": {"type": "string"}},
        "nota": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["titulo", "puntuacion", "aprobado", "estilo", "elementos", "nota"],
    "additionalProperties": False,
}


@pytest.fixture
def client() -> MockFoundryClient:
    return MockFoundryClient()


def png(size: tuple[int, int] = (64, 64), color: str = "#ffffff", mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, "PNG")
    return buffer.getvalue()


def test_factory_returns_mock_in_mock_mode() -> None:
    assert isinstance(create_foundry_client(Settings.load(env_file=None)), MockFoundryClient)


async def test_text_is_deterministic_and_identifies_role(client: MockFoundryClient) -> None:
    request = TextRequest(input="Salón de 4x6 m, estilo nórdico", instructions="Eres un experto")
    first = await client.complete_text(Role.PROMPT_ENGINEER, request)
    second = await client.complete_text(Role.PROMPT_ENGINEER, request)
    assert first.text == second.text
    assert "[MOCK PROMPT_ENGINEER]" in first.text
    assert first.deployment == "mock-prompt_engineer"
    assert first.usage.input_tokens > 0
    assert first.usage.output_tokens > 0
    assert first.usage.reasoning_tokens == 0


async def test_auditor_simulates_reasoning_tokens(client: MockFoundryClient) -> None:
    result = await client.complete_text(Role.GEOMETRIC_AUDITOR, TextRequest(input="Audita"))
    assert result.usage.reasoning_tokens > 0
    assert result.usage.output_tokens > result.usage.reasoning_tokens


async def test_images_add_input_tokens(client: MockFoundryClient) -> None:
    plain = await client.complete_text(Role.CONTEXT_MANAGER, TextRequest(input="x"))
    with_image = await client.complete_text(
        Role.CONTEXT_MANAGER, TextRequest(input="x", images=[InputImage(data=png())])
    )
    assert with_image.usage.input_tokens == plain.usage.input_tokens + 85


async def test_json_schema_returns_valid_data(client: MockFoundryClient) -> None:
    result = await client.complete_text(
        Role.PROMPT_ENGINEER, TextRequest(input="x", json_schema=SCHEMA)
    )
    assert result.data == {
        "titulo": "mock",
        "puntuacion": 1,
        "aprobado": True,
        "estilo": "nordico",
        "elementos": ["mock"],
        "nota": "mock",
    }
    assert sample_from_schema({"type": ["null", "number"]}) == 0.0


async def test_generate_images(client: MockFoundryClient) -> None:
    result = await client.generate_image(
        Role.FAST_DRAFT, ImageRequest(prompt="Salón nórdico", size="512x384", n=2)
    )
    assert len(result.images) == 2
    assert result.images[0].data != result.images[1].data
    for generated in result.images:
        with Image.open(io.BytesIO(generated.data)) as image:
            assert image.size == (512, 384)
            assert image.format == "PNG"
    assert result.usage.output_tokens > 0


async def test_jpeg_output_format(client: MockFoundryClient) -> None:
    result = await client.generate_image(
        Role.PHOTOREALISTIC_RENDERER, ImageRequest(prompt="x", size="256x256", output_format="jpeg")
    )
    assert result.images[0].mime_type == "image/jpeg"
    assert result.usage.total_tokens == 0  # el renderizador se factura por imagen


async def test_edit_with_mask_changes_only_masked_zone(client: MockFoundryClient) -> None:
    base = png((256, 256), "#ffffff")
    mask_image = Image.new("RGBA", (256, 256), (0, 0, 0, 255))
    mask_image.paste((0, 0, 0, 0), (0, 0, 128, 256))  # mitad izquierda transparente = editar
    buffer = io.BytesIO()
    mask_image.save(buffer, "PNG")

    result = await client.edit_image(
        Role.STRUCTURAL_COMPOSER,
        ImageEditRequest(
            prompt="Sofá gris",
            size="256x256",
            images=[InputImage(data=base)],
            mask=InputImage(data=buffer.getvalue()),
        ),
    )
    with Image.open(io.BytesIO(result.images[0].data)) as image:
        assert image.getpixel((250, 5)) == (255, 255, 255)  # fuera de la máscara: intacto
        assert image.getpixel((5, 5)) != (255, 255, 255)  # dentro: editado


@pytest.mark.parametrize(
    ("role", "operation"),
    [
        (Role.FAST_DRAFT, "text"),
        (Role.PHOTOREALISTIC_RENDERER, "text"),
        (Role.PROMPT_ENGINEER, "image"),
        (Role.GEOMETRIC_AUDITOR, "image"),
    ],
)
async def test_role_and_operation_must_match(
    client: MockFoundryClient, role: Role, operation: str
) -> None:
    with pytest.raises(FoundryUnsupportedError, match=role.value):
        if operation == "text":
            await client.complete_text(role, TextRequest(input="x"))
        else:
            await client.generate_image(role, ImageRequest(prompt="x"))


async def test_renderer_rejects_mask(client: MockFoundryClient) -> None:
    request = ImageEditRequest(
        prompt="x", images=[InputImage(data=png())], mask=InputImage(data=png())
    )
    with pytest.raises(FoundryUnsupportedError, match="STRUCTURAL_COMPOSER"):
        await client.edit_image(Role.PHOTOREALISTIC_RENDERER, request)


def test_invalid_image_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="size"):
        ImageRequest(prompt="x", size="grande")
