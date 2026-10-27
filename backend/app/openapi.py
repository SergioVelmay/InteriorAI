"""Exporta el esquema OpenAPI de la API para la documentación pública (Paso 35).

    uv run python -m app.openapi            # escribe docs/referencia/openapi.json

El archivo se versiona: así cada cambio de la API se ve en el diff de la Pull Request, y un test
(`backend/tests/test_api_openapi_export.py`) falla si no está al día. Se genera en modo mock,
sin `.env` ni acceso a `data/`.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from app.main import create_app
from shared import ProviderMode, Settings

OUTPUT = Path(__file__).resolve().parents[2] / "docs" / "referencia" / "openapi.json"


def schema() -> dict[str, Any]:
    """El esquema OpenAPI de la aplicación, sin depender de la configuración local."""
    settings = Settings.load(env_file=None)
    settings = settings.model_copy(
        update={"app": settings.app.model_copy(update={"ai_provider_mode": ProviderMode.MOCK})}
    )
    logging.disable(logging.WARNING)  # sin precios ni datos: sus avisos no vienen al caso
    try:
        return create_app(settings).openapi()
    finally:
        logging.disable(logging.NOTSET)


def render() -> str:
    return json.dumps(schema(), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str]) -> int:
    output = Path(argv[0]) if argv else OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(), encoding="utf-8", newline="\n")
    print(f"Esquema OpenAPI escrito en {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
