import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from tests.conftest import make_settings


def test_required_settings_have_no_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_ORIGIN", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    missing = {err["loc"][0] for err in exc.value.errors()}
    assert missing == {"app_env", "app_origin"}


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("APP_ORIGIN", "http://localhost:5173")
    settings = Settings(_env_file=None)
    assert settings.app_env == "local"
    assert settings.app_origin.host == "localhost"


def test_unknown_app_env_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(app_env="prod")


@pytest.mark.parametrize("env", ["staging", "production"])
def test_deployed_envs_refuse_http_origin(env: str) -> None:
    with pytest.raises(ValidationError, match="APP_ORIGIN must use https"):
        make_settings(app_env=env, app_origin="http://campussignal.example")


@pytest.mark.parametrize("env", ["staging", "production"])
def test_deployed_envs_accept_https_origin(env: str) -> None:
    assert make_settings(app_env=env, app_origin="https://campussignal.example").app_env == env


def test_api_docs_disabled_in_production() -> None:
    app = create_app(make_settings(app_env="production", app_origin="https://cs.example"))
    assert app.openapi_url is None
    assert app.docs_url is None


def test_api_docs_enabled_locally() -> None:
    app = create_app(make_settings(app_env="local"))
    assert app.openapi_url == "/api/v1/openapi.json"
