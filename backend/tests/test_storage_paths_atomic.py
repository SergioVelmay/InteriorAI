import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.storage import atomic
from app.storage.atomic import CorruptDataError, read_json, write_json_atomic
from app.storage.paths import InvalidPathError, ProjectPaths, safe_join, stored_asset_name
from shared.models import AssetKind


class Doc(BaseModel):
    value: int


# --- Rutas -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_id", ["../etc", "..", "", "abc", "00000000-0000-0000-0000-00000000000g"]
)
def test_project_paths_reject_non_uuid(tmp_path: Path, bad_id: str) -> None:
    with pytest.raises(InvalidPathError):
        ProjectPaths(tmp_path, bad_id)


@pytest.mark.parametrize("parts", [("..", "x"), ("a", "..", ".."), ("/etc/passwd",), (".",)])
def test_safe_join_rejects_escapes(tmp_path: Path, parts: tuple[str, ...]) -> None:
    with pytest.raises(InvalidPathError):
        safe_join(tmp_path, *parts)


def test_asset_path_cannot_escape_project(tmp_path: Path) -> None:
    paths = ProjectPaths(tmp_path, uuid4())
    with pytest.raises(InvalidPathError):
        paths.asset(AssetKind.PLANO, "../../../proyectos.json")


@pytest.mark.parametrize(
    ("original", "ext"),
    [
        ("plano.PNG", "png"),
        ("foto.jpeg", "jpeg"),
        ("../../etc/passwd", "bin"),
        ("..\\..\\evil.exe", "exe"),
        ("sin_extension", "bin"),
        ("raro.p n g", "bin"),
        ("largo.extensionlarga", "bin"),
    ],
)
def test_stored_name_ignores_user_filename(original: str, ext: str) -> None:
    asset_id = uuid4()
    assert stored_asset_name(asset_id, original) == f"{asset_id}.{ext}"


# --- Escritura atómica -----------------------------------------------------------------


def test_write_and_read_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "doc.json"
    write_json_atomic(path, Doc(value=1))
    assert read_json(path, Doc).value == 1
    assert json.loads(path.read_text(encoding="utf-8")) == {"value": 1}


def test_failed_write_keeps_original_and_leaves_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "doc.json"
    write_json_atomic(path, Doc(value=1))

    def crash(*_: object) -> None:
        raise OSError("disco lleno (simulado)")

    monkeypatch.setattr(atomic.os, "replace", crash)
    with pytest.raises(OSError, match="simulado"):
        write_json_atomic(path, Doc(value=2))
    assert read_json(path, Doc).value == 1
    assert os.listdir(tmp_path) == ["doc.json"]


def test_replace_retries_transient_permission_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simula el bloqueo momentáneo del destino por antivirus/indexador en Windows."""
    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src: str, dst: str) -> None:
        calls["n"] += 1
        if calls["n"] <= 3:
            raise PermissionError("Access is denied (simulado)")
        real_replace(src, dst)

    monkeypatch.setattr(atomic, "REPLACE_BACKOFF_S", 0)
    monkeypatch.setattr(atomic.os, "replace", flaky)
    path = tmp_path / "doc.json"
    write_json_atomic(path, Doc(value=7))
    assert calls["n"] == 4
    assert read_json(path, Doc).value == 7


def test_replace_gives_up_after_max_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_locked(*_: object) -> None:
        raise PermissionError("Access is denied (simulado)")

    monkeypatch.setattr(atomic, "REPLACE_BACKOFF_S", 0)
    monkeypatch.setattr(atomic.os, "replace", always_locked)
    with pytest.raises(PermissionError):
        write_json_atomic(tmp_path / "doc.json", Doc(value=1))
    assert os.listdir(tmp_path) == []


@pytest.mark.parametrize("content", ["{no es json", '{"value": "texto"}', ""])
def test_corrupt_json_raises_clear_error(tmp_path: Path, content: str) -> None:
    path = tmp_path / "doc.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(CorruptDataError, match=r"doc.json"):
        read_json(path, Doc)
