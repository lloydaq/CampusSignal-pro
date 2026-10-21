"""Application settings, loaded from environment variables (architecture.md §19)."""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

AppEnv = Literal["local", "ci", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

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

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def docs_enabled(self) -> bool:
        return self.app_env in ("local", "ci")

    @model_validator(mode="after")
    def _refuse_insecure_deployed_config(self) -> "Settings":
        if self.app_env in ("staging", "production") and self.app_origin.scheme != "https":
            raise ValueError(f"APP_ORIGIN must use https when APP_ENV={self.app_env}")
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
