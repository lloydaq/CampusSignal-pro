"""Application settings, loaded from environment variables (architecture.md §19)."""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

AppEnv = Literal["local", "ci", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
EmailBackend = Literal["smtp", "memory"]
SmtpSecurity = Literal["none", "starttls", "tls"]

DATABASE_DRIVER = "postgresql+psycopg"
LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
SECURE_SSLMODES = frozenset({"require", "verify-ca", "verify-full"})


class Settings(BaseSettings):
    # hide_input_in_errors: validation errors must never echo DATABASE_URL (it holds a password).
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", frozen=True, hide_input_in_errors=True
    )

    # Required: no defaults, so a missing variable fails startup instead of
    # silently running with development behaviour.
    app_env: AppEnv
    app_origin: AnyHttpUrl
    database_url: SecretStr
    log_level: LogLevel = "INFO"

    # Sessions (AUTH-004, AUTH-013, P-10). Privileged = faculty/admin roles and platform admins.
    session_idle_days: int = Field(default=7, ge=1, le=90)
    session_absolute_days: int = Field(default=30, ge=1, le=365)
    privileged_session_idle_hours: int = Field(default=24, ge=1, le=168)
    privileged_session_absolute_days: int = Field(default=7, ge=1, le=30)

    # Number of reverse proxies in front of the API that append to X-Forwarded-For (Caddy = 1).
    # 0 uses the direct connection address; client-supplied forwarding headers are never
    # trusted beyond this many hops (architecture.md §10).
    trusted_proxy_count: int = Field(default=0, ge=0, le=5)

    # Email (architecture.md §15). "smtp" sends via SMTP (Mailpit locally on port 1025);
    # "memory" keeps messages in-process for tests. There is deliberately no console
    # backend: emails carry tokens, which must never reach logs (Rules R-2.11).
    email_backend: EmailBackend = "smtp"
    email_from: str = "CampusSignal <no-reply@campussignal.localhost>"
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_security: SmtpSecurity = "none"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def docs_enabled(self) -> bool:
        return self.app_env in ("local", "ci")

    @model_validator(mode="after")
    def _refuse_insecure_deployed_config(self) -> "Settings":
        if self.app_env in ("staging", "production"):
            if self.app_origin.scheme != "https":
                raise ValueError(f"APP_ORIGIN must use https when APP_ENV={self.app_env}")
            if self.email_backend != "smtp":
                raise ValueError(f"EMAIL_BACKEND must be smtp when APP_ENV={self.app_env}")
            if self.smtp_security == "none":
                raise ValueError(
                    f"SMTP_SECURITY must be starttls or tls when APP_ENV={self.app_env}"
                )
        return self

    @model_validator(mode="after")
    def _privileged_sessions_not_looser(self) -> "Settings":
        if self.privileged_session_idle_hours > self.session_idle_days * 24:
            raise ValueError("PRIVILEGED_SESSION_IDLE_HOURS must not exceed SESSION_IDLE_DAYS")
        if self.privileged_session_absolute_days > self.session_absolute_days:
            raise ValueError(
                "PRIVILEGED_SESSION_ABSOLUTE_DAYS must not exceed SESSION_ABSOLUTE_DAYS"
            )
        return self

    @model_validator(mode="after")
    def _validate_database_url(self) -> "Settings":
        # Messages name the problem only; they never include the URL itself.
        try:
            url = make_url(self.database_url.get_secret_value())
        except ArgumentError:
            raise ValueError("DATABASE_URL is not a valid database URL") from None
        if url.drivername != DATABASE_DRIVER:
            raise ValueError(f"DATABASE_URL must start with {DATABASE_DRIVER}://")
        if url.host not in LOCAL_DB_HOSTS and url.query.get("sslmode") not in SECURE_SSLMODES:
            raise ValueError(
                "DATABASE_URL for a non-local host must set sslmode=require "
                "(or verify-ca / verify-full)"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
