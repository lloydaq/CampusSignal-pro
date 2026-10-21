"""Migration round trips, model drift and readiness against a disposable Postgres 17."""

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.main import create_app
from tests.conftest import make_settings

pytestmark = pytest.mark.integration


def _citext_installed(engine: Engine) -> bool:
    with engine.connect() as conn:
        found = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'citext'"))
        return found.scalar() is not None


def test_upgrade_downgrade_upgrade_roundtrip(config: Config, engine: Engine) -> None:
    command.downgrade(config, "base")
    assert not _citext_installed(engine)

    command.upgrade(config, "head")
    assert _citext_installed(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 'A'::citext = 'a'::citext")).scalar() is True

    command.downgrade(config, "base")
    assert not _citext_installed(engine)
    command.upgrade(config, "head")
    assert _citext_installed(engine)


def test_models_match_migrations(config: Config) -> None:
    command.upgrade(config, "head")
    command.check(config)  # raises if models have changes without a migration


def test_readyz_ready_after_upgrade_and_pending_after_downgrade(
    config: Config, test_database_url: str
) -> None:
    app = create_app(make_settings(database_url=test_database_url))
    command.upgrade(config, "head")
    with TestClient(app) as client:
        assert client.get("/readyz").json() == {"status": "ready"}
        command.downgrade(config, "base")
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["error"]["details"] == {"migrations": "pending"}
    command.upgrade(config, "head")
