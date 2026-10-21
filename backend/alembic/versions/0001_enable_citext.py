"""Enable the citext extension (case-insensitive text for emails; architecture.md §8.1).

Installed in the default `public` schema so the same migration works on Supabase and on
the plain Postgres 17 used in CI. citext is a trusted extension, so the migrating role
needs only CREATE privilege on the database, not superuser.

Downgrade drops the extension. That is safe at this revision because nothing depends on
it yet; later revisions that add citext columns must be downgraded first.

Revision ID: 0001
Revises:
Create Date: 2026-10-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS citext")
