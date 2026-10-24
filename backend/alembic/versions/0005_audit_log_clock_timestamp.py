"""Audit entries take the moment they are written, not the transaction's start time.

`now()` returns the start of the current transaction, so several audit entries written in one
transaction (or one request) shared a timestamp and their order fell back to random UUIDs.
`clock_timestamp()` is the actual time of the insert. Existing rows are unchanged.

Downgrade restores `now()`.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("audit_log", "created_at", server_default=sa.text("clock_timestamp()"))


def downgrade() -> None:
    op.alter_column("audit_log", "created_at", server_default=sa.text("now()"))
