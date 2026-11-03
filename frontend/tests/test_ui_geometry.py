"""Geometría frente al esquema 3D (B-116): aristas, fidelidad y superposición."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ui.geometry import fidelity, overlay, sketch_edges


def scheme(path: Path, shift: int = 0, filled: bool = True) -> Path:
    """Un esquema a lo SketchUp: colores planos, aristas negras finas y una superficie oscura."""
    image = Image.new("RGB", (600, 400), (240, 240, 240))
    draw = ImageDraw.Draw(image)
    draw.rectangle((100 + shift, 120, 300 + shift, 330), fill=(1, 94, 95), outline=(0, 0, 0))
    draw.rectangle((340 + shift, 60, 520 + shift, 200), fill=(241, 228, 193), outline=(0, 0, 0))
    if filled:
        draw.rectangle((20, 20, 70, 380), fill=(10, 10, 10))  # superficie oscura, no arista
    image.save(path)
    return path


def test_sketch_edges_keep_thin_black_lines_and_skip_dark_surfaces(tmp_path: Path) -> None:
    edges = sketch_edges(str(scheme(tmp_path / "a.png")))
    assert edges[120, 200] and edges[330, 200]  # aristas de la caja
    assert not edges[200, 45]  # dentro de la superficie oscura, nada
    assert not edges[200, 200]  # dentro de la caja, nada


def test_fidelity_is_full_on_itself_and_drops_when_geometry_moves(tmp_path: Path) -> None:
    sketch = scheme(tmp_path / "esquema.png")
    same = fidelity(sketch, sketch)
    assert same.near > 0.95 and same.loose > 0.95
    near_miss = fidelity(sketch, scheme(tmp_path / "a5.png", shift=5))  # 5 px: dentro de ±8
    far = fidelity(sketch, scheme(tmp_path / "a20.png", shift=20))
    assert near_miss.near < same.near and near_miss.loose > 0.8
    assert far.loose < near_miss.loose
    assert "a ±3 px" in same.label() and "a ±8 px" in same.label()


def test_overlay_paints_the_sketch_edges_at_the_image_size(tmp_path: Path) -> None:
    sketch = scheme(tmp_path / "esquema.png")
    photo = tmp_path / "foto.png"
    Image.new("RGB", (900, 600), (120, 120, 120)).save(photo)  # mayor que el esquema
    result = np.asarray(overlay(sketch, photo, opacity=1.0))
    assert result.shape == (600, 900, 3)
    assert tuple(result[180, 300]) == (239, 68, 68)  # arista superior de la caja, escalada
    assert tuple(result[300, 300]) == (120, 120, 120)  # el resto, intacto
