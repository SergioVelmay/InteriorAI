import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from shared import Settings

_PREFIXES = ("AI_", "AZURE_", "DEPLOYMENT_ROLE_", "DATA_DIR", "LOG_", "APP_")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.upper().startswith(_PREFIXES):
            monkeypatch.delenv(key)


def make_client(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    return TestClient(create_app(Settings.load(env_file=None)))


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with make_client(monkeypatch, tmp_path / "data") as c:
        yield c


def test_health_ok_in_mock_mode(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "mock"
    assert body["data_dir_writable"] is True
    assert body["version"]


def test_startup_creates_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "nested" / "data"
    with make_client(monkeypatch, data_dir):
        assert data_dir.is_dir()


def test_health_degraded_when_data_dir_unusable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x", encoding="utf-8")
    with make_client(monkeypatch, not_a_dir) as c:
        response = c.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_openapi_docs_available(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "InteriorAI API"
