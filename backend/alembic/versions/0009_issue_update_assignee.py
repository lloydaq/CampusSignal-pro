"""Issue timeline: who an assignment was to (ISSUE-004, 005).

An ASSIGNMENT row in `issue_updates` names the member the issue was assigned to, or NULL when
it was unassigned. The member is in the issue's college (composite foreign key); other kinds of
row name nobody. The append-only trigger from 0008 is unaffected: rows are still only inserted.

Downgrade drops the column (assignment rows then no longer say to whom).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("issue_updates", sa.Column("assignee_membership_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_issue_updates_assignee_membership",
        "issue_updates",
        "college_memberships",
        ["college_id", "assignee_membership_id"],
        ["college_id", "id"],
    )
    op.create_check_constraint(
        op.f("ck_issue_updates_assignee_only_on_assignment"),
        "issue_updates",
        "kind = 'ASSIGNMENT' OR assignee_membership_id IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_issue_updates_assignee_only_on_assignment"), "issue_updates", type_="check"
    )
    op.drop_constraint("fk_issue_updates_assignee_membership", "issue_updates", type_="foreignkey")
    op.drop_column("issue_updates", "assignee_membership_id")
