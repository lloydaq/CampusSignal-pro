"""Uvicorn entry points resolve exactly as the documented commands load them.

Regression: `uvicorn app.main:app` failed with 'Attribute "app" not found in module
"app.main"'. Uvicorn's own importer is used so the test matches real startup. Settings
come from monkeypatched environment variables (which take precedence over any local
.env) pointing at an unreachable database: nothing here connects anywhere.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from uvicorn.importer import import_from_string

import app.main as main_module
from app.core.config import get_settings
from tests.conftest import UNREACHABLE_DB_URL

EXPECTED_ROUTES = {"/healthz", "/readyz"}


@pytest.fixture
def startup_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("APP_ENV", "ci")
    monkeypatch.setenv("APP_ORIGIN", "http://localhost:5173")
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DB_URL)
    get_settings.cache_clear()
    vars(main_module).pop("app", None)
    yield
    vars(main_module).pop("app", None)  # drop the cached app so tests stay independent
    get_settings.cache_clear()


def _assert_serves_health_routes(app: FastAPI) -> None:
    assert set(app.openapi()["paths"]) >= EXPECTED_ROUTES
    with TestClient(app) as client:  # runs the real lifespan; /healthz needs no database
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "X-Request-ID" in response.headers


def test_importing_main_does_not_build_the_app() -> None:
    # Module import must stay free of settings/.env side effects.
    assert "app" not in vars(main_module)


@pytest.mark.usefixtures("startup_env")
def test_uvicorn_app_main_app_resolves() -> None:
    app = import_from_string("app.main:app")
    assert isinstance(app, FastAPI)
    _assert_serves_health_routes(app)
    assert app.state.settings.app_env == "ci"
    # Cached: uvicorn workers and repeated lookups get the same instance.
    assert import_from_string("app.main:app") is app


@pytest.mark.usefixtures("startup_env")
def test_uvicorn_factory_entry_point_resolves() -> None:
    factory = import_from_string("app.main:app_factory")
    app = factory()
    assert isinstance(app, FastAPI)
    _assert_serves_health_routes(app)


def test_unknown_attribute_still_raises() -> None:
    with pytest.raises(AttributeError, match="no attribute 'not_an_app'"):
        _ = main_module.not_an_app
