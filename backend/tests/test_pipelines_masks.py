"""Máscaras de retoque y recomposición local exacta (B-009), tamaño del render final (B-018)."""

import io
from uuid import uuid4

import pytest
from PIL import Image

from app.pipelines import masks
from app.pipelines.errors import PipelineInputError
from app.pipelines.renders import generation_size, renderer_size
from shared.models import Asset, AssetKind
from shared.roles import Role


def png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def painted(size: tuple[int, int], box: tuple[int, int, int, int]) -> bytes:
    mask = Image.new("RGBA", size, (0, 0, 0, 0))
    mask.paste((255, 255, 255, 255), box)
    return png(mask)


def test_edit_zone_from_alpha_or_luminance() -> None:
    zone = masks.edit_zone(painted((300, 200), (30, 20, 60, 40)), (600, 400))
    assert zone.size == (600, 400) and zone.mode == "L"
    assert zone.getpixel((100, 50)) == 255 and zone.getpixel((10, 10)) == 0

    bw = Image.new("L", (600, 400), 0)
    bw.paste(255, (0, 0, 60, 40))
    zone = masks.edit_zone(png(bw), (600, 400))
    assert masks.coverage(zone) == pytest.approx(60 * 40 / (600 * 400))


def test_edit_zone_rejects_other_proportions_and_non_images() -> None:
    with pytest.raises(PipelineInputError, match="proporción"):
        masks.edit_zone(painted((400, 400), (0, 0, 10, 10)), (600, 400))
    with pytest.raises(PipelineInputError, match="no es una imagen"):
        masks.edit_zone(b"nada", (600, 400))


@pytest.mark.parametrize(
    ("box", "message"), [((0, 0, 0, 0), "vacía"), ((0, 0, 600, 400), "casi toda")]
)
def test_coverage_limits(box: tuple[int, int, int, int], message: str) -> None:
    mask = Image.new("RGBA", (600, 400), (0, 0, 0, 0))
    if box[2]:
        mask.paste((255, 255, 255, 255), box)
    with pytest.raises(PipelineInputError, match=message):
        masks.check_coverage(masks.edit_zone(png(mask), (600, 400)))


def test_model_mask_is_transparent_where_to_edit() -> None:
    zone = masks.edit_zone(painted((600, 400), (0, 0, 300, 400)), (600, 400))
    with Image.open(io.BytesIO(masks.model_mask(zone, (300, 200)))) as mask:
        assert mask.size == (300, 200) and mask.mode == "RGBA"
        assert mask.getpixel((10, 10))[3] == 0 and mask.getpixel((290, 10))[3] == 255


def asset(width: int | None, height: int | None) -> Asset:
    return Asset(
        id=uuid4(), kind=AssetKind.REFERENCIA, stored_name="x.png", original_name="x.png",
        mime_type="image/png", size_bytes=1, sha256="0" * 64, width_px=width, height_px=height,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((1600, 900), "1920x1080"),  # 16:9 exacto
        ((3000, 2000), "1920x1280"),  # 3:2
        ((900, 1200), "1440x1920"),  # 3:4 vertical
        ((1000, 1000), "1536x1536"),
        ((None, None), None),
    ],
)
def test_renderer_size_follows_the_capture(size: tuple, expected: str | None) -> None:
    assert renderer_size(asset(*size)) == expected


@pytest.mark.parametrize(
    ("role", "size", "expected"),
    [
        (Role.PHOTOREALISTIC_RENDERER, "1920x1080", "1920x1088"),
        (Role.PHOTOREALISTIC_RENDERER, "1920x1280", "1920x1280"),
        (Role.PHOTOREALISTIC_RENDERER, "1081x1919", "1088x1920"),
        (Role.STRUCTURAL_COMPOSER, "1536x1024", "1536x1024"),
    ],
)
def test_generation_size_rounds_up_to_16(role: Role, size: str, expected: str) -> None:
    assert generation_size(role, size) == expected


def test_fit_crops_the_center_without_scaling() -> None:
    image = Image.new("RGB", (1920, 1088), "#000000")
    image.paste("#ff0000", (0, 0, 1920, 4))  # franjas que deben desaparecer
    image.paste("#00ff00", (0, 1084, 1920, 1088))
    image.paste("#808080", (0, 4, 1920, 1084))
    fitted = masks.fit(image, (1920, 1080))
    assert fitted.size == (1920, 1080)
    assert fitted.getcolors() == [(1920 * 1080, (128, 128, 128))]
    assert masks.fit(image, (1920, 1088)) is image
    # Otra proporción: recorta lo que sobra y escala.
    assert masks.fit(Image.new("RGB", (1536, 1024)), (1920, 1080)).size == (1920, 1080)
