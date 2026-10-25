"""Tamaños del render final (Paso 24, B-040), compartidos por el backend y la interfaz.

El renderizador fotorrealista admite hasta 4 MP en múltiplos de 16 px. Por proporción hay tres
resoluciones (decisión del usuario): la mínima, igual o lo más parecida posible a las de los
modelos GPT de imagen (1536x1024, 1024x1024, 1024x1536); la máxima, la mayor que cabe en 4 MP; y
la intermedia, en el punto medio del lado largo (en 3:2, la más cercana con la proporción exacta).
Todas con la proporción exacta: el modelo no tiene que redondear ni se recorta nada.
"""

from __future__ import annotations

RENDERER_SIZES: dict[str, list[str]] = {
    "16:9": ["1536x864", "2048x1152", "2560x1440"],
    "3:2": ["1536x1024", "2016x1344", "2448x1632"],
    "1:1": ["1024x1024", "1504x1504", "1984x1984"],
    "2:3": ["1024x1536", "1344x2016", "1632x2448"],
    "9:16": ["864x1536", "1152x2048", "1440x2560"],
}
DEFAULT_RATIO = "3:2"  # la de las composiciones
DEFAULT_RENDERER_SIZE = RENDERER_SIZES[DEFAULT_RATIO][-1]  # la máxima


def megapixels(size: str) -> float:
    width, height = (int(v) for v in size.split("x"))
    return width * height / 1_000_000
