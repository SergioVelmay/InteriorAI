"""Geometría frente al esquema 3D (B-116, Pasos 47 y 49): las aristas de la imagen base (un
esquema de SketchUp con aristas negras y colores planos), su superposición sobre una imagen
generada y la fidelidad geométrica (qué parte de esas aristas tiene una arista de la imagen
cerca), tal cual y ajustando el desplazamiento global del encuadre.

Solo análisis, sin tocar las imágenes: la superposición es una vista, no un retoque. El ajuste
mueve las aristas del esquema para medir, nunca la imagen generada.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

DARK = 45  # gris por debajo del cual un píxel es negro de arista (los colores oscuros, no)
THIN = 5  # lado del núcleo: lo oscuro más grueso que esto es una superficie, no una arista
TOLERANCES = (3, 8)  # píxeles a la escala del esquema
EDGE_COLOR = (239, 68, 68)  # rojo de la superposición
SEARCH_WIDTH = 320  # ancho al que se busca el desplazamiento (el afinado va a tamaño completo)
REFINE_SHIFT = 6  # píxeles del esquema que explora la búsqueda fina a cada lado
REACH = 0.20  # desplazamiento máximo que se explora, en parte del ancho y del alto
MARGIN = 0.002  # lo que tiene que mejorar un desplazamiento para preferirlo a quedarse quieto
TIGHT_WEIGHT = 0.01  # peso del ±3 px: desempata entre desplazamientos que a ±8 px empatan


@dataclass(frozen=True)
class Fidelity:
    near: float  # aristas del esquema con una arista de la imagen a ±3 px
    loose: float  # a ±8 px (cubre cantos redondeados de pocos píxeles)

    def label(self) -> str:
        return f"{self.near:.0%} a ±{TOLERANCES[0]} px · {self.loose:.0%} a ±{TOLERANCES[1]} px"


@dataclass(frozen=True)
class Alignment:
    """El encuadre de la imagen frente al esquema: cuánto hay que mover las aristas del esquema
    para que encajen lo mejor posible, y la fidelidad una vez movidas."""

    dx: int  # desplazamiento horizontal en píxeles del esquema (+ a la derecha)
    dy: int  # vertical (+ hacia abajo)
    fit: Fidelity  # fidelidad con ese desplazamiento ya aplicado

    def shift_label(self) -> str:
        horizontal = (
            f"{abs(self.dx)} px a la {'derecha' if self.dx > 0 else 'izquierda'}"
            if self.dx
            else "sin desplazamiento horizontal"
        )
        vertical = (
            f"{abs(self.dy)} px {'abajo' if self.dy > 0 else 'arriba'}"
            if self.dy
            else "sin desplazamiento vertical"
        )
        return f"{horizontal} · {vertical}"

    def label(self) -> str:
        return f"{self.shift_label()} · {self.fit.label()}"


def _gray(path: str | Path, size: tuple[int, int] | None = None) -> np.ndarray:
    with Image.open(path) as image:
        gray = image.convert("L")
        if size is not None and gray.size != size:
            gray = gray.resize(size, Image.Resampling.LANCZOS)
        return np.asarray(gray)


@lru_cache(maxsize=32)
def sketch_edges(path: str) -> np.ndarray:
    """Aristas del esquema: los trazos negros finos (sin las superficies oscuras rellenas, que
    quita una apertura morfológica) y los cambios entre colores planos."""
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    dark = (gray < DARK).astype(np.uint8)
    filled = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((THIN, THIN), np.uint8))
    lines = dark & (1 - filled)
    flat = cv2.Canny(cv2.GaussianBlur(rgb, (3, 3), 0), 40, 120) > 0
    edges = (lines.astype(bool) | flat) & ~(filled.astype(bool))
    height, width = edges.shape
    # La marca de agua de SketchUp (abajo, en el centro) no es geometría.
    edges[int(height * 0.9) :, int(width * 0.38) : int(width * 0.62)] = False
    return edges


@lru_cache(maxsize=256)
def _photo_edges(path: str, size: tuple[int, int]) -> np.ndarray:
    """Aristas estructurales de una imagen generada, a la escala del esquema: se suaviza antes
    para que no cuenten las texturas finas (vetas, tejidos)."""
    gray = cv2.bilateralFilter(_gray(path, size), 9, 50, 7)
    high = float(np.percentile(gray, 99) - np.percentile(gray, 1)) or 1.0
    return cv2.Canny(gray, 0.15 * high, 0.35 * high) > 0


def _near_maps(found: np.ndarray) -> tuple[np.ndarray, ...]:
    """Las aristas de la imagen engordadas a cada tolerancia: dónde vale caer."""
    maps = []
    for tolerance in TOLERANCES:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * tolerance + 1,) * 2)
        maps.append(cv2.dilate(found, kernel).astype(bool))
    return tuple(maps)


def fidelity(sketch: str | Path, image: str | Path) -> Fidelity:
    edges = sketch_edges(str(sketch))
    size = (edges.shape[1], edges.shape[0])
    found = _photo_edges(str(image), size).astype(np.uint8)
    total = int(edges.sum()) or 1
    return Fidelity(*(float((edges & near).sum()) / total for near in _near_maps(found)))


# --- Encuadre: el desplazamiento global (Paso 49) ---------------------------------------------


def _window(
    spectrum: np.ndarray, template: np.ndarray, padded: tuple[int, int], shape: tuple[int, int]
) -> np.ndarray:
    """Para cada desplazamiento, cuántas aristas del esquema caen sobre el mapa del que se pasa el
    espectro. Por correlación (FFT): se prueban todos los desplazamientos de una vez."""
    correlation = np.fft.irfft2(spectrum * np.fft.rfft2(template[::-1, ::-1], padded), padded)
    up, side = int(shape[0] * REACH), int(shape[1] * REACH)
    centre_y, centre_x = shape[0] - 1, shape[1] - 1  # ahí está el desplazamiento (0, 0)
    return correlation[centre_y - up : centre_y + up + 1, centre_x - side : centre_x + side + 1]


def _points(edges: np.ndarray, limit: int = 6000) -> tuple[np.ndarray, np.ndarray]:
    """Las aristas del esquema como coordenadas, aligeradas para la búsqueda fina."""
    rows, columns = np.nonzero(edges)
    step = len(rows) // limit + 1
    return rows[::step], columns[::step]


def _share(points: tuple[np.ndarray, np.ndarray], near: np.ndarray, dx: int, dy: int) -> float:
    """Parte de las aristas del esquema que, movidas así, caen sobre una arista de la imagen."""
    rows, columns = points
    height, width = near.shape
    moved_y, moved_x = rows + dy, columns + dx
    inside = (moved_y >= 0) & (moved_y < height) & (moved_x >= 0) & (moved_x < width)
    if not inside.any():
        return 0.0
    return float(near[moved_y[inside], moved_x[inside]].sum()) / (len(rows) or 1)


@lru_cache(maxsize=256)
def _alignment(sketch: str, image: str) -> Alignment:
    edges = sketch_edges(sketch)
    height, width = edges.shape
    found = _photo_edges(image, (width, height)).astype(np.uint8)
    near = _near_maps(found)
    # Mapa de puntuación: 1 donde hay arista a ±8 px y algo más donde además la hay a ±3 px, así
    # dos desplazamientos que a ±8 px empatan se desempatan por el ajuste fino.
    guide = near[1].astype(np.float32) + TIGHT_WEIGHT * near[0]
    # 1. Búsqueda gruesa a baja resolución: todos los desplazamientos de una vez.
    factor = min(1.0, SEARCH_WIDTH / width)
    small_edges = cv2.resize(edges.astype(np.float32), None, fx=factor, fy=factor)
    small_guide = cv2.resize(guide, None, fx=factor, fy=factor)
    shape = small_guide.shape
    padded = (2 * shape[0], 2 * shape[1])  # relleno: así la correlación no da la vuelta
    hits = _window(np.fft.rfft2(small_guide, padded), small_edges, padded, shape)
    up, side = int(shape[0] * REACH), int(shape[1] * REACH)
    row, column = np.unravel_index(int(np.argmax(hits)), hits.shape)
    coarse = (round(float(column - side) / factor), round(float(row - up) / factor))
    # 2. Afinado a tamaño completo. Se parte de quedarse quieto, así el ajuste nunca sale peor que
    #    el esquema tal cual, y solo se mueve si mejora de verdad.
    light = _points(edges)
    chosen, score = (0, 0), _share(light, guide, 0, 0)
    for down in sorted(range(-REFINE_SHIFT, REFINE_SHIFT + 1), key=abs):
        for right in sorted(range(-REFINE_SHIFT, REFINE_SHIFT + 1), key=abs):
            candidate = (coarse[0] + right, coarse[1] + down)
            value = _share(light, guide, *candidate)
            if value > score + MARGIN:
                chosen, score = candidate, value
    dx, dy = chosen
    shares = [_share(np.nonzero(edges), one, dx, dy) for one in near]
    return Alignment(dx=dx, dy=dy, fit=Fidelity(*shares))


def alignment(sketch: str | Path, image: str | Path) -> Alignment:
    """El desplazamiento del encuadre de la imagen frente al esquema, y la fidelidad con él."""
    return _alignment(str(sketch), str(image))


# --- Superposición ----------------------------------------------------------------------------


def _warped(edges: np.ndarray, fit: Alignment | None) -> np.ndarray:
    """Las aristas del esquema con el desplazamiento aplicado. Se mueve el esquema, nunca la
    imagen generada."""
    if fit is None or (fit.dx == 0 and fit.dy == 0):
        return edges
    height, width = edges.shape
    matrix = np.array([[1.0, 0.0, fit.dx], [0.0, 1.0, fit.dy]], np.float32)
    return cv2.warpAffine(edges, matrix, (width, height), flags=cv2.INTER_NEAREST)


def _captioned(picture: Image.Image, text: str) -> Image.Image:
    """El texto en rojo sobre la imagen, arriba a la izquierda, con reborde oscuro para que se
    lea sobre cualquier fondo."""
    size = max(14, picture.width // 48)
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:  # Pillow sin tamaño en la fuente por defecto
        font = ImageFont.load_default()
    margin = max(8, picture.width // 120)
    ImageDraw.Draw(picture).text(
        (margin, margin), text, font=font, fill=EDGE_COLOR,
        stroke_width=max(1, size // 10), stroke_fill=(17, 17, 17), spacing=size // 3,
    )  # fmt: skip
    return picture


def overlay(
    sketch: str | Path,
    image: str | Path,
    opacity: float = 0.8,
    fit: Alignment | None = None,
    caption: str = "",
) -> Image.Image:
    """La imagen generada con las aristas del esquema encima, en rojo, a su tamaño. Con `fit`, las
    aristas van con el encuadre ajustado; con `caption`, el dato en rojo sobre la imagen."""
    with Image.open(image) as opened:
        base = np.asarray(opened.convert("RGB")).astype(np.float32)
    edges = _warped(sketch_edges(str(sketch)).astype(np.uint8), fit)
    height, width = base.shape[:2]
    drawn_width = edges.shape[1]
    if edges.shape != (height, width):
        edges = cv2.resize(edges, (width, height), interpolation=cv2.INTER_NEAREST)
    if width > drawn_width * 1.2:  # imagen mayor que el esquema: trazo algo más grueso
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8))
    mask = edges.astype(bool)
    alpha = min(max(opacity, 0.0), 1.0)
    base[mask] = base[mask] * (1 - alpha) + np.array(EDGE_COLOR, np.float32) * alpha
    picture = Image.fromarray(base.clip(0, 255).astype(np.uint8))
    return _captioned(picture, caption) if caption else picture
