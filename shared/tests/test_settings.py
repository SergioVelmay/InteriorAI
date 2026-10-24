import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared import settings as settings_module
from shared.roles import ApiKind, Role
from shared.settings import ProviderMode, Settings

FAKE_KEY = "fake-key-for-tests-0000-wxyz"

AZURE_ENV = {
    "AI_PROVIDER_MODE": "azure",
    "AZURE_FOUNDRY_ENDPOINT": "https://example.com",
    "AZURE_FOUNDRY_API_KEY": FAKE_KEY,
    "AZURE_FOUNDRY_RENDERER_PATH": "/providers/example/v1/renderer",
    **{role.env_var: f"deploy-{role.value.lower()}" for role in Role},
}

_PREFIXES = (
    "APP_", "LOG_", "AI_", "AZURE_", "DEPLOYMENT_ROLE_", "GEOMETRIC_AUDITOR_",
    "DATA_DIR", "PRICING_", "MAX_UPLOAD", "BACKEND_", "FRONTEND_", "COST_ALERT_",
)  # fmt: skip


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla los tests de variables reales de la máquina."""
    for key in list(os.environ):
        if key.upper().startswith(_PREFIXES):
            monkeypatch.delenv(key)


def write_env(tmp_path: Path, values: dict[str, str]) -> Path:
    path = tmp_path / ".env"
    path.write_text("\n".join(f"{k}={v}" for k, v in values.items()), encoding="utf-8")
    return path


def load(tmp_path: Path, values: dict[str, str]) -> Settings:
    return Settings.load(env_file=write_env(tmp_path, values))


# --- Valores por defecto y carga -----------------------------------------------------


def test_defaults_are_mock_and_need_no_credentials() -> None:
    s = Settings.load(env_file=None)
    assert s.app.ai_provider_mode is ProviderMode.MOCK
    assert s.is_mock
    assert s.foundry.endpoint is None
    assert s.foundry.api_key is None
    assert s.storage.data_dir == Path("/app/data")
    assert s.storage.max_upload_bytes == 25 * 1024 * 1024


def test_loads_values_from_env_file(tmp_path: Path) -> None:
    s = load(tmp_path, AZURE_ENV | {"LOG_LEVEL": "debug", "MAX_UPLOAD_MB": "40"})
    assert s.app.ai_provider_mode is ProviderMode.AZURE
    assert s.app.log_level == "DEBUG"
    assert s.foundry.endpoint == "https://example.com"
    assert s.foundry.api_key is not None
    assert s.foundry.api_key.get_secret_value() == FAKE_KEY
    assert s.storage.max_upload_mb == 40


def test_process_env_overrides_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    s = load(tmp_path, {"LOG_LEVEL": "INFO"})
    assert s.app.log_level == "ERROR"


def test_blank_values_are_treated_as_unset(tmp_path: Path) -> None:
    s = load(
        tmp_path,
        {
            "AZURE_FOUNDRY_ENDPOINT": "",
            "AZURE_FOUNDRY_API_KEY": "",
            "AZURE_FOUNDRY_API_VERSION": "",
            "AZURE_FOUNDRY_RENDERER_ENDPOINT": "",
            "DEPLOYMENT_ROLE_FAST_DRAFT": "",
        },
    )
    assert s.foundry.endpoint is None
    assert s.foundry.api_key is None
    assert s.foundry.api_version is None
    assert s.foundry.renderer_endpoint is None
    assert s.deployments.get(Role.FAST_DRAFT) is None


# --- Modo azure ------------------------------------------------------------------------


def test_azure_mode_requires_credentials_and_deployments(tmp_path: Path) -> None:
    with pytest.raises(ValidationError) as exc:
        load(tmp_path, {"AI_PROVIDER_MODE": "azure"})
    message = str(exc.value)
    for var in ("AZURE_FOUNDRY_ENDPOINT", "AZURE_FOUNDRY_API_KEY", "AZURE_FOUNDRY_RENDERER_PATH"):
        assert var in message
    for role in Role:
        assert role.env_var in message


def test_azure_mode_complete_is_valid(tmp_path: Path) -> None:
    s = load(tmp_path, AZURE_ENV)
    assert s.azure_missing() == []


def test_mock_mode_reports_missing_azure_vars_without_failing(tmp_path: Path) -> None:
    s = load(tmp_path, {"AZURE_FOUNDRY_ENDPOINT": "https://example.com"})
    assert "AZURE_FOUNDRY_API_KEY" in s.azure_missing()
    assert "AZURE_FOUNDRY_ENDPOINT" not in s.azure_missing()


# --- Validación de endpoints -----------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.com/openai/v1/responses",
        "https://example.com/openai/v1/",
        "https://example.com/?api-version=1",
    ],
)
def test_endpoint_with_path_or_query_is_rejected(tmp_path: Path, endpoint: str) -> None:
    with pytest.raises(ValidationError, match="solo el host"):
        load(tmp_path, {"AZURE_FOUNDRY_ENDPOINT": endpoint})


@pytest.mark.parametrize("endpoint", ["http://example.com", "example.com", "ftp://example.com"])
def test_endpoint_must_be_https(tmp_path: Path, endpoint: str) -> None:
    with pytest.raises(ValidationError, match="https"):
        load(tmp_path, {"AZURE_FOUNDRY_ENDPOINT": endpoint})


def test_endpoint_trailing_slash_is_normalized(tmp_path: Path) -> None:
    s = load(tmp_path, {"AZURE_FOUNDRY_ENDPOINT": "https://example.com/"})
    assert s.foundry.endpoint == "https://example.com"


def test_renderer_endpoint_falls_back_to_main(tmp_path: Path) -> None:
    s = load(tmp_path, AZURE_ENV)
    assert s.foundry.renderer_base_url == "https://example.com"
    s = load(tmp_path, AZURE_ENV | {"AZURE_FOUNDRY_RENDERER_ENDPOINT": "https://other.example"})
    assert s.foundry.renderer_base_url == "https://other.example"


@pytest.mark.parametrize("path", ["providers/x", "https://example.com/providers/x"])
def test_renderer_path_must_be_relative_path(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValidationError, match="ruta"):
        load(tmp_path, {"AZURE_FOUNDRY_RENDERER_PATH": path})


# --- Secretos --------------------------------------------------------------------------


def test_api_key_never_leaks_in_representations(tmp_path: Path) -> None:
    s = load(tmp_path, AZURE_ENV)
    for text in (str(s), repr(s), s.model_dump_json(), str(s.model_dump())):
        assert FAKE_KEY not in text
    assert FAKE_KEY not in settings_module.render_report(s)


def test_invalid_config_error_output_hides_input_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_env(tmp_path, {"AZURE_FOUNDRY_ENDPOINT": f"https://example.com/{FAKE_KEY}"})
    monkeypatch.chdir(tmp_path)
    assert settings_module.main() == 1
    out = capsys.readouterr().out
    assert "solo el host" in out
    assert FAKE_KEY not in out


def test_cli_report_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_env(tmp_path, AZURE_ENV)
    monkeypatch.chdir(tmp_path)
    assert settings_module.main() == 0
    out = capsys.readouterr().out
    assert "Listo para modo azure: SÍ" in out
    assert "****wxyz" in out


# --- Roles -----------------------------------------------------------------------------


@pytest.mark.parametrize("role", list(Role))
def test_each_role_resolves_to_its_deployment(tmp_path: Path, role: Role) -> None:
    s = load(tmp_path, AZURE_ENV)
    assert s.deployment_for(role) == f"deploy-{role.value.lower()}"


def test_mock_mode_has_placeholder_deployments() -> None:
    s = Settings.load(env_file=None)
    assert s.deployment_for(Role.FAST_DRAFT) == "mock-fast_draft"


def test_every_role_has_an_api_kind() -> None:
    assert {role.api_kind for role in Role} == set(ApiKind)
    assert Role.GEOMETRIC_AUDITOR.api_kind is ApiKind.RESPONSES
    assert Role.PHOTOREALISTIC_RENDERER.api_kind is ApiKind.PROVIDER_IMAGES


def test_settings_are_immutable() -> None:
    s = Settings.load(env_file=None)
    with pytest.raises(ValidationError):
        s.app = s.app  # type: ignore[misc]


def test_auditor_defaults_medium_effort_and_own_timeout() -> None:
    s = Settings.load(env_file=None)
    assert s.auditor.reasoning_effort == "medium"
    assert s.auditor.timeout_s == 900


def test_cost_alert_thresholds(tmp_path: Path) -> None:
    defaults = Settings.load(env_file=None).cost_alerts
    assert (defaults.project_eur, defaults.total_eur) == (3.0, 10.0)
    custom = load(tmp_path, {"COST_ALERT_PROJECT_EUR": "1.5", "COST_ALERT_TOTAL_EUR": "20"})
    assert (custom.cost_alerts.project_eur, custom.cost_alerts.total_eur) == (1.5, 20.0)
    with pytest.raises(ValidationError):
        load(tmp_path, {"COST_ALERT_PROJECT_EUR": "0"})
