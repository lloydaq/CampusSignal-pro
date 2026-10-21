"""Revoke Supabase API-role privileges in the public schema (architecture.md §9, ADR-14).

CampusSignal accesses PostgreSQL only through the backend (direct SQL over the session
pooler). Supabase's Data API roles `anon` and `authenticated` must not be able to read or
write application objects, even if the Data API is switched back on: disabling the Data
API does not remove PostgreSQL grants.

What this revision does, for each of `anon` and `authenticated` that exists:
- revokes all privileges on existing tables, views and sequences in `public`
  (including `alembic_version`);
- revokes the default privileges that Supabase configures for objects the migrating role
  (`current_user`, `postgres` on Supabase) creates in `public` later: tables, sequences
  and functions.

Assumptions:
- Migrations always run as the same role that owns application objects. Default
  privileges are per creating role; a different migrating role would need this applied
  again.
- Default privileges held by `supabase_admin` (which also grants these roles access in
  `public`) cannot be changed by `postgres` and are left alone; that role never creates
  CampusSignal tables. Existing functions in `public` belong to the citext extension and
  are owned by `supabase_admin`, so they are not touched either.
- `service_role` is not changed: its key is a server-side secret and the backend does
  not use it.
- Where the roles do not exist (plain PostgreSQL, e.g. CI), this revision is a no-op.

Downgrade is intentionally a no-op: re-granting broad privileges to the public API roles
would reopen the exposure this revision closes. No schema objects are created here, so
revision 0001 runs correctly with the privileges still revoked.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            api_role text;
        BEGIN
            FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
                    -- quote_ident() rather than format() placeholders: the SQL has no
                    -- percent signs, so it is identical online and rendered with --sql.
                    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM '
                        || quote_ident(api_role);
                    EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM '
                        || quote_ident(api_role);
                    EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE ' || quote_ident(current_user)
                        || ' IN SCHEMA public REVOKE ALL ON TABLES FROM '
                        || quote_ident(api_role);
                    EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE ' || quote_ident(current_user)
                        || ' IN SCHEMA public REVOKE ALL ON SEQUENCES FROM '
                        || quote_ident(api_role);
                    EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE ' || quote_ident(current_user)
                        || ' IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM '
                        || quote_ident(api_role);
                END IF;
            END LOOP;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Intentionally empty: see module docstring (restoring the grants would be insecure).
    pass
