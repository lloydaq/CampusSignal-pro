"""Application settings, loaded from environment variables (architecture.md §19)."""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["local", "ci", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    # Required: no defaults, so a missing variable fails startup instead of
    # silently running with development behaviour.
    app_env: AppEnv
    app_origin: AnyHttpUrl
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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
