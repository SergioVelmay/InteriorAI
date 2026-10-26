"""Previsión del tiempo de las acciones de IA (B-064).

Gradio muestra en cada acción «procesando | transcurrido/previsto», y su previsión es la media de
las ejecuciones anteriores del mismo botón, que guarda en memoria y pierde al reiniciarse. Sin
historial no muestra nada. Aquí se siembra la previsión medida en las pruebas reales para que se
vea desde la primera vez; en cuanto termina la primera ejecución real, se descarta y Gradio
sigue con su media normal.

Usa un detalle interno de Gradio (`Queue.process_time_per_fn`): lo vigila un test.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import gradio as gr
from gradio.queueing import ProcessTime

# Segundos medidos en las pruebas reales (Pasos 21-24), por tipo de acción.
FORECAST_S = {
    "analisis": 45.0,  # receta de una referencia
    "bocetos": 35.0,  # 4 bocetos
    "auditoria": 30.0,
    "composicion": 35.0,  # composición o retoque
    "render_final": 30.0,
    "otra_version": 25.0,
}


class Forecast(ProcessTime):
    """Media de Gradio que empieza con la previsión y la descarta en la primera ejecución
    real (`ProcessTime.add` suma sobre `count = 0`)."""

    def __init__(self, seconds: float) -> None:
        super().__init__()
        self.avg_time = seconds


def seed_forecasts(demo: gr.Blocks, dependencies: Iterable[tuple[dict[str, Any], float]]) -> int:
    """Siembra la previsión de cada evento ({dependencia de Gradio, segundos}); devuelve cuántas."""
    queue = demo._queue
    seeded = 0
    for dependency, seconds in dependencies:
        function = demo.fns[dependency["id"]]
        if function not in queue.process_time_per_fn:
            queue.process_time_per_fn[function] = Forecast(seconds)
            seeded += 1
    return seeded
