"""Geometría frente al esquema 3D (B-116, Paso 47): las aristas de la imagen base (un esquema de
SketchUp con aristas negras y colores planos), su superposición sobre una imagen generada y la
fidelidad geométrica (qué parte de esas aristas tiene una arista de la imagen cerca).

Solo análisis, sin tocar las imágenes: la superposición es una vista, no un retoque.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

DARK = 45  # gris por debajo del cual un píxel es negro de arista (los colores oscuros, no)
THIN = 5  # lado del núcleo: lo oscuro más grueso que esto es una superficie, no una arista
TOLERANCES = (3, 8)  # píxeles a la escala del esquema
EDGE_COLOR = (239, 68, 68)  # rojo de la superposición


@dataclass(frozen=True)
class Fidelity:
    near: float  # aristas del esquema con una arista de la imagen a ±3 px
    loose: float  # a ±8 px (cubre cantos redondeados de pocos píxeles)

    def label(self) -> str:
        return f"{self.near:.0%} a ±{TOLERANCES[0]} px · {self.loose:.0%} a ±{TOLERANCES[1]} px"


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


def fidelity(sketch: str | Path, image: str | Path) -> Fidelity:
    edges = sketch_edges(str(sketch))
    size = (edges.shape[1], edges.shape[0])
    found = _photo_edges(str(image), size).astype(np.uint8)
    total = int(edges.sum()) or 1
    shares = []
    for tolerance in TOLERANCES:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * tolerance + 1,) * 2)
        near = cv2.dilate(found, kernel).astype(bool)
        shares.append(float((edges & near).sum()) / total)
    return Fidelity(*shares)


def overlay(sketch: str | Path, image: str | Path, opacity: float = 0.8) -> Image.Image:
    """La imagen generada con las aristas del esquema encima, en rojo, a su tamaño."""
    with Image.open(image) as opened:
        base = np.asarray(opened.convert("RGB")).astype(np.float32)
    edges = sketch_edges(str(sketch)).astype(np.uint8)
    height, width = base.shape[:2]
    if edges.shape != (height, width):
        edges = cv2.resize(edges, (width, height), interpolation=cv2.INTER_NEAREST)
    if width > edges.shape[1] * 1.2:  # imagen mayor que el esquema: trazo algo más grueso
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8))
    mask = edges.astype(bool)
    alpha = min(max(opacity, 0.0), 1.0)
    base[mask] = base[mask] * (1 - alpha) + np.array(EDGE_COLOR, np.float32) * alpha
    return Image.fromarray(base.clip(0, 255).astype(np.uint8))
