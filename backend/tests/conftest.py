import io
import json
import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from shared import Settings

_PREFIXES = (
    "AI_", "AZURE_", "DEPLOYMENT_ROLE_", "GEOMETRIC_AUDITOR_", "DATA_DIR", "LOG_", "APP_",
    "MAX_UPLOAD", "PRICING_",
)  # fmt: skip
PRICING_FILE = Path(__file__).resolve().parents[2] / "config" / "pricing.yaml"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla los tests de variables reales de la máquina."""
    for key in list(os.environ):
        if key.upper().startswith(_PREFIXES):
            monkeypatch.delenv(key)


@pytest.fixture
def make_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[..., TestClient]]:
    """Fábrica de clientes con `DATA_DIR` temporal; admite `max_upload_mb`."""
    clients: list[TestClient] = []

    def factory(max_upload_mb: int | None = None) -> TestClient:
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("PRICING_FILE", str(PRICING_FILE))
        if max_upload_mb is not None:
            monkeypatch.setenv("MAX_UPLOAD_MB", str(max_upload_mb))
        client = TestClient(create_app(Settings.load(env_file=None)))
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def api(make_api: Callable[..., TestClient]) -> TestClient:
    return make_api()


def mark_legacy(api: TestClient, project_id: str, kinds: dict[str, str]) -> None:
    """Simula imágenes migradas de la v1 (B-028): `legacy_kind` por id de asset."""
    path = api.app.state.settings.storage.data_dir / project_id / "metadatos.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for asset in data["assets"]:
        asset["legacy_kind"] = kinds.get(asset["id"], asset.get("legacy_kind"))
    path.write_text(json.dumps(data), encoding="utf-8")


def image_bytes(
    fmt: str = "PNG", size: tuple[int, int] = (64, 48), color: str = "#8b5cf6", mode: str = "RGB"
) -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, format=fmt)
    return buffer.getvalue()
