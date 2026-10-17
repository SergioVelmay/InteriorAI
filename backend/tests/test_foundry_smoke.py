"""Script de verificación: doble seguro y flujo completo, siempre con el cliente simulado."""

import json
from pathlib import Path

import pytest

from app.foundry import FoundryBadRequestError, MockFoundryClient, TextRequest, TextResult
from app.foundry.smoke import main
from shared import Settings
from shared.roles import Role


def azure_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effort: str = "max") -> None:
    monkeypatch.chdir(tmp_path)  # sin .env real
    values = {
        "AI_PROVIDER_MODE": "azure",
        "AZURE_FOUNDRY_ENDPOINT": "https://example.com",
        "AZURE_FOUNDRY_API_KEY": "fake-key-for-tests-0000",
        "AZURE_FOUNDRY_RENDERER_PATH": "/providers/proveedor/v1/renderer",
        "GEOMETRIC_AUDITOR_REASONING_EFFORT": effort,
        **{role.env_var: f"dep-{role.value.lower()}" for role in Role},
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def never_called(_: Settings) -> MockFoundryClient:
    raise AssertionError("no debe crearse ningún cliente")


def test_refuses_to_run_in_mock_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["--out", str(tmp_path)], client_factory=never_called) == 2
    assert "Bloqueado" in capsys.readouterr().out


def test_answering_no_skips_every_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    azure_env(monkeypatch, tmp_path)
    calls: list[str] = []

    class Spy(MockFoundryClient):
        async def _complete_text(self, role, request):  # pragma: no cover - no debe llamarse
            calls.append(role.value)
            return await super()._complete_text(role, request)

    assert main(["--out", str(tmp_path / "out")], lambda s: Spy(), lambda _: "n") == 0
    report = json.loads((tmp_path / "out" / "informe.json").read_text(encoding="utf-8"))
    assert [o["status"] for o in report] == ["skipped"] * 6
    assert calls == []


def test_full_plan_with_mock_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    azure_env(monkeypatch, tmp_path)
    out = tmp_path / "out"
    assert main(["--out", str(out)], lambda s: MockFoundryClient(), lambda _: "s") == 0
    report = json.loads((out / "informe.json").read_text(encoding="utf-8"))
    assert [o["key"] for o in report] == ["1", "2", "3", "4", "5", "6"]
    assert all(o["status"] == "ok" for o in report)
    assert report[1]["data"] == {"estilo": "mock", "colores": ["mock"]}
    assert report[2]["usage"]["reasoning_tokens"] > 0
    images = sorted(p.name for p in out.glob("*.*") if p.suffix in {".png", ".jpeg"})
    assert images == [
        "4_fast_draft_0.png",
        "5_structural_composer_0.png",
        "6_photorealistic_renderer_0.jpeg",
    ]


def test_single_role_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    azure_env(monkeypatch, tmp_path)
    out = tmp_path / "out"
    argv = ["--role", "FAST_DRAFT", "--out", str(out)]
    assert main(argv, lambda s: MockFoundryClient(), lambda _: "s") == 0
    report = json.loads((out / "informe.json").read_text(encoding="utf-8"))
    assert [o["role"] for o in report] == ["FAST_DRAFT"]


def test_auditor_falls_back_to_high_when_max_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    azure_env(monkeypatch, tmp_path, effort="max")

    class EffortAware(MockFoundryClient):
        def __init__(self, settings: Settings) -> None:
            super().__init__()
            self.effort = settings.auditor.reasoning_effort

        async def _complete_text(self, role: Role, request: TextRequest) -> TextResult:
            if role is Role.GEOMETRIC_AUDITOR and self.effort == "max":
                raise FoundryBadRequestError("Unsupported value 'max'", role=role, status_code=400)
            return await super()._complete_text(role, request)

    out = tmp_path / "out"
    argv = ["--role", "GEOMETRIC_AUDITOR", "--out", str(out)]
    assert main(argv, EffortAware, lambda _: "s") == 1  # la llamada con max falló
    report = json.loads((out / "informe.json").read_text(encoding="utf-8"))
    assert [(o["key"], o["status"]) for o in report] == [("3", "error"), ("3b", "ok")]
    assert report[0]["error"] == "FoundryBadRequestError"
