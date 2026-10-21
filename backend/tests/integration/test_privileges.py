"""Migration 0002: Supabase API roles get no privileges in `public` (disposable Postgres 17).

Plain Postgres has no `anon`/`authenticated` roles, so one test checks the migration is a
no-op without them and the other recreates Supabase's grants to check they are revoked.
Roles are cluster-wide: tests create them only if absent and drop what they created.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text

pytestmark = pytest.mark.integration

API_ROLES = ("anon", "authenticated")
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")


def _role_exists(conn: Connection, role: str) -> bool:
    found = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role})
    return found.scalar() is not None


def _grant_like_supabase(conn: Connection) -> None:
    """Recreate the grants Supabase gives the API roles (as observed on the dev project)."""
    for role in API_ROLES:
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
        conn.execute(text(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {role}"))
        conn.execute(text(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {role}"))
        for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            conn.execute(
                text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON {kind} TO {role}")
            )


def _drop_api_roles(conn: Connection) -> None:
    for role in API_ROLES:
        if _role_exists(conn, role):
            conn.execute(text(f"DROP OWNED BY {role}"))
            conn.execute(text(f"DROP ROLE {role}"))


@pytest.fixture
def supabase_like_roles(engine: Engine) -> Iterator[None]:
    with engine.begin() as conn:
        if any(_role_exists(conn, role) for role in API_ROLES):
            pytest.skip("API roles already exist on this server; refusing to modify them")
        for role in API_ROLES:
            conn.execute(text(f"CREATE ROLE {role} NOLOGIN"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS privilege_probe"))
        conn.execute(text("DROP SEQUENCE IF EXISTS privilege_probe_seq"))
        _drop_api_roles(conn)


def _table_privileges(conn: Connection, role: str, table: str) -> list[str]:
    return [
        privilege
        for privilege in TABLE_PRIVILEGES
        if conn.execute(
            text("SELECT has_table_privilege(:r, :t, :p)"), {"r": role, "t": table, "p": privilege}
        ).scalar()
    ]


def _sequence_privileges(conn: Connection, role: str, sequence: str) -> list[str]:
    return [
        privilege
        for privilege in ("USAGE", "SELECT", "UPDATE")
        if conn.execute(
            text("SELECT has_sequence_privilege(:r, :s, :p)"),
            {"r": role, "s": sequence, "p": privilege},
        ).scalar()
    ]


def test_migration_is_noop_without_supabase_roles(config: Config, engine: Engine) -> None:
    with engine.connect() as conn:
        if any(_role_exists(conn, role) for role in API_ROLES):
            pytest.skip("API roles exist on this server")
    command.downgrade(config, "base")
    command.upgrade(config, "head")  # must not fail when the roles are absent


@pytest.mark.usefixtures("supabase_like_roles")
def test_api_roles_lose_existing_and_default_privileges(config: Config, engine: Engine) -> None:
    command.downgrade(config, "base")
    command.upgrade(config, "0001")
    with engine.begin() as conn:
        _grant_like_supabase(conn)
        assert _table_privileges(conn, "anon", "public.alembic_version")  # precondition

    command.upgrade(config, "0002")

    with engine.begin() as conn:
        for role in API_ROLES:
            assert _table_privileges(conn, role, "public.alembic_version") == []
        # Objects created afterwards by the migrating role get no API-role privileges.
        conn.execute(text("CREATE TABLE privilege_probe (id integer PRIMARY KEY)"))
        conn.execute(text("CREATE SEQUENCE privilege_probe_seq"))
        for role in API_ROLES:
            assert _table_privileges(conn, role, "public.privilege_probe") == []
            assert _sequence_privileges(conn, role, "public.privilege_probe_seq") == []
        remaining = conn.execute(
            text(
                "SELECT count(*) FROM pg_default_acl d "
                "JOIN pg_namespace n ON n.oid = d.defaclnamespace, aclexplode(d.defaclacl) a "
                "WHERE n.nspname = 'public' "
                "AND d.defaclrole = (SELECT oid FROM pg_roles WHERE rolname = current_user) "
                "AND a.grantee IN "
                "(SELECT oid FROM pg_roles WHERE rolname IN ('anon', 'authenticated'))"
            )
        ).scalar()
        assert remaining == 0


@pytest.mark.usefixtures("supabase_like_roles")
def test_downgrade_to_0001_keeps_privileges_revoked(config: Config, engine: Engine) -> None:
    command.downgrade(config, "base")
    command.upgrade(config, "0001")
    with engine.begin() as conn:
        _grant_like_supabase(conn)
    command.upgrade(config, "0002")
    command.downgrade(config, "0001")  # documented no-op: must not re-grant
    with engine.connect() as conn:
        for role in API_ROLES:
            assert _table_privileges(conn, role, "public.alembic_version") == []
    command.upgrade(config, "head")
