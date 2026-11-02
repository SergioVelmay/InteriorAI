"""Bloqueos inmediatos en el navegador (Pasos 41 y 42): un formulario se bloquea en el mismo clic,
sin esperar a la ida y vuelta al servidor; la respuesta del servidor lo desbloquea después."""

from __future__ import annotations

import json


def lock_js(*selectors: str) -> str:
    """JS de un evento: desactiva los campos y botones de `selectors` (los de dentro de cada
    elemento, o el propio elemento si es un botón) y no cambia las entradas del evento."""
    targets = json.dumps(", ".join(f"{s} textarea, {s} input, button{s}" for s in selectors))
    return f"""(...args) => {{
    document.querySelectorAll({targets}).forEach((el) => {{ el.disabled = true; }});
    return args;
}}"""
