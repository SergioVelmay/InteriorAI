"""Importes en la interfaz (Paso 39): estimaciones y resúmenes, al céntimo hacia arriba, para ver
siempre en Azure menos gasto del previsto. Los importes guardados siguen exactos (las sumas se
hacen antes de redondear) y el registro de llamadas los muestra con 4 decimales."""

from __future__ import annotations

import math


def cents_up(value: float) -> float:
    """Al céntimo hacia arriba (0,0014 → 0,01; 0,07 → 0,07, sin errores de coma flotante)."""
    return math.ceil(round(value * 100, 6)) / 100


def euros_up(value: float | None, missing: str = "sin precio") -> str:
    return missing if value is None else f"{cents_up(value):.2f} €"
