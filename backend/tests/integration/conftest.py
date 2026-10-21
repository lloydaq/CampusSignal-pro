"""Shared setup for integration tests against a disposable Postgres 17 (CI service).

These tests downgrade migrations and create cluster roles, so they run only against a
database positively identified as disposable (see `disposable_database_problem`), and
the whole run stops otherwise. They read TEST_DATABASE_URL only: never DATABASE_URL or
a developer's .env. Without TEST_DATABASE_URL they skip, unless
CAMPUSSIGNAL_REQUIRE_INTEGRATION=1 (set in CI), where they fail instead.
"""

import os
from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.db import alembic_config, create_db_engine
from tests.conftest import disposable_database_problem, make_settings

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
REQUIRE_INTEGRATION = os.environ.get("CAMPUSSIGNAL_REQUIRE_INTEGRATION") == "1"


@pytest.fixture(scope="session")
def _verified_disposable_database() -> str:
    if TEST_DATABASE_URL is None:
        if REQUIRE_INTEGRATION:
            pytest.fail("TEST_DATABASE_URL must be set when CAMPUSSIGNAL_REQUIRE_INTEGRATION=1")
        pytest.skip("TEST_DATABASE_URL not set (integration tests run in CI)")
    problem = disposable_database_problem(TEST_DATABASE_URL)
    if problem is not None:
        pytest.exit(f"Refusing destructive integration tests: {problem}", returncode=2)

    # Positive check on the live server before anything destructive happens.
    engine = create_db_engine(make_settings(database_url=TEST_DATABASE_URL))
    try:
        with engine.connect() as conn:
            current_db = conn.execute(text("SELECT current_database()")).scalar()
            supabase = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = 'supabase_admin'")
            ).scalar()
    finally:
        engine.dispose()
    if current_db != make_url(TEST_DATABASE_URL).database:
        pytest.exit("Refusing: connected database does not match TEST_DATABASE_URL", returncode=2)
    if supabase is not None:
        pytest.exit("Refusing: server has Supabase roles; not a disposable database", returncode=2)
    return TEST_DATABASE_URL


@pytest.fixture(autouse=True)
def _require_disposable_database(_verified_disposable_database: str) -> None:
    """Every integration test depends on the verified-disposable check."""


@pytest.fixture
def test_database_url(_verified_disposable_database: str) -> str:
    return _verified_disposable_database


@pytest.fixture
def engine(test_database_url: str) -> Iterator[Engine]:
    engine = create_db_engine(make_settings(database_url=test_database_url))
    yield engine
    engine.dispose()


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch, test_database_url: str) -> Iterator[Config]:
    # alembic/env.py reads DATABASE_URL through app settings: point it at the test DB
    # explicitly so it can never fall back to a developer's .env.
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("APP_ENV", "ci")
    monkeypatch.setenv("APP_ORIGIN", "http://localhost:5173")
    get_settings.cache_clear()
    cfg = alembic_config()
    cfg.attributes["configure_logger"] = False
    yield cfg
    get_settings.cache_clear()
