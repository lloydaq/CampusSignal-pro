from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.main import create_app

# Hosted Supabase databases: pooler hosts end in supabase.com, direct hosts in supabase.co.
SUPABASE_HOST_SUFFIXES = (".supabase.com", ".supabase.co")

# What a browser sends from the SPA: state-changing requests carry this Origin (AUTH-008).
APP_ORIGIN = "http://localhost:5173"

# Port 1 on loopback is closed: unit tests never reach a real database or the network.
UNREACHABLE_DB_URL = (
    "postgresql+psycopg://campussignal:not-a-real-password@127.0.0.1:1/campussignal"
)


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "ci",
        "app_origin": APP_ORIGIN,
        "database_url": UNREACHABLE_DB_URL,
        "email_backend": "memory",
    }
    values.update(overrides)
    # _env_file=None: tests must not depend on a developer's local .env.
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def is_hosted_supabase(database_url: str) -> bool:
    """True for any Supabase-hosted database; destructive tests must refuse these."""
    host = (make_url(database_url).host or "").lower().rstrip(".")
    return host.endswith(SUPABASE_HOST_SUFFIXES)


LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
DISPOSABLE_DB_SUFFIX = "_test"


def disposable_database_problem(database_url: str) -> str | None:
    """Why `database_url` is not positively a disposable test database, or None if it is.

    Destructive integration tests require: a Supabase-free loopback host (CI's service
    container is reached via localhost) and a database name ending in `_test`. Messages
    never include the URL.
    """
    try:
        url = make_url(database_url)
    except Exception:
        return "TEST_DATABASE_URL is not a valid database URL"
    if is_hosted_supabase(database_url):
        return "TEST_DATABASE_URL points at a hosted Supabase database"
    if (url.host or "").lower() not in LOOPBACK_HOSTS:
        return "TEST_DATABASE_URL host must be localhost / 127.0.0.1 / ::1"
    if not (url.database or "").endswith(DISPOSABLE_DB_SUFFIX):
        return f"TEST_DATABASE_URL database name must end with {DISPOSABLE_DB_SUFFIX!r}"
    return None


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False, headers={"Origin": APP_ORIGIN}) as c:
        yield c


@pytest.fixture
def bare_client(app: FastAPI) -> Iterator[TestClient]:
    """A client that sends no Origin, for tests of the Origin check itself."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
