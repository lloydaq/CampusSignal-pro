"""Migration scripts rendered offline (`alembic upgrade --sql`): no database or network."""

from collections.abc import Iterator

import pytest
from alembic import command

from app.core.config import get_settings
from app.core.db import alembic_config
from tests.conftest import UNREACHABLE_DB_URL


@pytest.fixture
def offline_sql(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Iterator[str]:
    monkeypatch.setenv("APP_ENV", "ci")
    monkeypatch.setenv("APP_ORIGIN", "http://localhost:5173")
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DB_URL)
    get_settings.cache_clear()
    config = alembic_config()
    config.attributes["configure_logger"] = False
    command.upgrade(config, "base:head", sql=True)
    yield capsys.readouterr().out
    get_settings.cache_clear()


def test_offline_sql_enables_citext_in_public(offline_sql: str) -> None:
    assert "CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public" in offline_sql


def test_offline_sql_revokes_api_roles_only_when_present(offline_sql: str) -> None:
    assert "ARRAY['anon', 'authenticated']" in offline_sql
    assert "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role)" in offline_sql
    assert "%" not in offline_sql  # percent signs would be doubled by --sql rendering
    for statement in (
        "'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM '",
        "'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM '",
        "' IN SCHEMA public REVOKE ALL ON TABLES FROM '",
        "' IN SCHEMA public REVOKE ALL ON SEQUENCES FROM '",
        "' IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM '",
    ):
        assert statement in offline_sql
    assert "'ALTER DEFAULT PRIVILEGES FOR ROLE ' || quote_ident(current_user)" in offline_sql
    assert "quote_ident(api_role)" in offline_sql
    # Never re-grants anything to the API roles.
    assert "GRANT" not in offline_sql.replace("ALTER DEFAULT PRIVILEGES", "")


def test_offline_sql_contains_no_credentials(offline_sql: str) -> None:
    assert "not-a-real-password" not in offline_sql
    assert "127.0.0.1" not in offline_sql
