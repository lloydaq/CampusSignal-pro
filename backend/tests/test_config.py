import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from tests.conftest import UNREACHABLE_DB_URL, make_settings

# Email settings a deployed environment must have (SMTP with TLS).
DEPLOYED_EMAIL = {"email_backend": "smtp", "smtp_security": "tls"}


def test_required_settings_have_no_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_ORIGIN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    missing = {err["loc"][0] for err in exc.value.errors()}
    assert missing == {"app_env", "app_origin", "database_url"}


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("APP_ORIGIN", "http://localhost:5173")
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DB_URL)
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
    settings = make_settings(
        app_env=env, app_origin="https://campussignal.example", **DEPLOYED_EMAIL
    )
    assert settings.app_env == env


def test_api_docs_disabled_in_production() -> None:
    app = create_app(
        make_settings(app_env="production", app_origin="https://cs.example", **DEPLOYED_EMAIL)
    )
    assert app.openapi_url is None
    assert app.docs_url is None


def test_api_docs_enabled_locally() -> None:
    app = create_app(make_settings(app_env="local"))
    assert app.openapi_url == "/api/v1/openapi.json"


@pytest.mark.parametrize("env", ["staging", "production"])
def test_deployed_envs_refuse_in_memory_email(env: str) -> None:
    with pytest.raises(ValidationError, match="EMAIL_BACKEND must be smtp"):
        make_settings(app_env=env, app_origin="https://cs.example", email_backend="memory")


@pytest.mark.parametrize("env", ["staging", "production"])
def test_deployed_envs_refuse_unencrypted_smtp(env: str) -> None:
    with pytest.raises(ValidationError, match="SMTP_SECURITY must be starttls or tls"):
        make_settings(
            app_env=env, app_origin="https://cs.example", email_backend="smtp", smtp_security="none"
        )


def test_session_defaults_match_prd() -> None:
    settings = make_settings()
    assert (settings.session_idle_days, settings.session_absolute_days) == (7, 30)
    assert (settings.privileged_session_idle_hours, settings.privileged_session_absolute_days) == (
        24,
        7,
    )


def test_privileged_sessions_cannot_be_looser_than_standard() -> None:
    with pytest.raises(ValidationError, match="PRIVILEGED_SESSION_IDLE_HOURS"):
        make_settings(session_idle_days=1, privileged_session_idle_hours=48)
    with pytest.raises(ValidationError, match="PRIVILEGED_SESSION_ABSOLUTE_DAYS"):
        make_settings(session_absolute_days=5, privileged_session_absolute_days=7)


def test_smtp_password_never_shown() -> None:
    settings = make_settings(smtp_username="mailer", smtp_password="smtp-s3cret")
    assert "smtp-s3cret" not in repr(settings)
    assert "smtp-s3cret" not in str(settings.model_dump())
