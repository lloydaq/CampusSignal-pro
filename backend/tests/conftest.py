from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"app_env": "ci", "app_origin": "http://localhost:5173"}
    values.update(overrides)
    # _env_file=None: tests must not depend on a developer's local .env.
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
