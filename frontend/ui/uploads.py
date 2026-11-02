"""Copias temporales de las subidas de Gradio (B-108): se borran al cancelar, al quitar la imagen
o al subirla; nunca algo fuera de la carpeta de subidas de Gradio."""

from __future__ import annotations

import contextlib
from pathlib import Path

from gradio.utils import get_upload_folder

# Gradio borra además, cada hora, las subidas de más de un día que nadie haya usado (`app.py`).
DELETE_CACHE = (3600, 86400)


def discard_upload(path: str | None) -> bool:
    """Borra la copia temporal de una subida (y su carpeta, si queda vacía). Devuelve si borró."""
    if not path:
        return False
    file = Path(path).resolve()
    if not file.is_relative_to(Path(get_upload_folder()).resolve()) or not file.is_file():
        return False
    file.unlink(missing_ok=True)
    with contextlib.suppress(OSError):  # la carpeta de la subida, si queda vacía
        file.parent.rmdir()
    return True
