"""Campus issues (ISSUE-001…009).

Two tables. `campus_issues` holds the issue; its reporter, assignee and the issue it duplicates
are in the same college (composite foreign keys), a duplicate is always rejected, and only a
resolved issue has a resolution time. `issue_updates` is the timeline, append-only: a trigger
refuses UPDATE and DELETE (ISSUE-005: immutable).

Downgrade drops both tables (and with them every issue) and the trigger function.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = "'SUBMITTED', 'ACKNOWLEDGED', 'IN_PROGRESS', 'RESOLVED', 'REJECTED'"


def _timestamp(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "campus_issues",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("reporter_membership_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location_text", sa.Text(), nullable=False),
        sa.Column("room", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'SUBMITTED'"), nullable=False),
        sa.Column("assignee_membership_id", sa.Uuid(), nullable=True),
        sa.Column("duplicate_of_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reporter_reopen_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name=op.f("ck_campus_issues_status")),
        sa.CheckConstraint(
            "category IN ('CLASSROOM_EQUIPMENT', 'INFRASTRUCTURE', 'WATER_SANITATION', "
            "'ELECTRICAL', 'NETWORK', 'LIBRARY', 'LABORATORY', 'OTHER')",
            name=op.f("ck_campus_issues_category"),
        ),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 120", name=op.f("ck_campus_issues_title_length")
        ),
        sa.CheckConstraint(
            "char_length(description) BETWEEN 1 AND 3000",
            name=op.f("ck_campus_issues_description_length"),
        ),
        sa.CheckConstraint(
            "char_length(location_text) BETWEEN 1 AND 200",
            name=op.f("ck_campus_issues_location_length"),
        ),
        sa.CheckConstraint(
            "room IS NULL OR char_length(room) BETWEEN 1 AND 100",
            name=op.f("ck_campus_issues_room_length"),
        ),
        sa.CheckConstraint(
            "duplicate_of_id IS NULL OR duplicate_of_id <> id",
            name=op.f("ck_campus_issues_not_own_duplicate"),
        ),
        sa.CheckConstraint(
            "duplicate_of_id IS NULL OR status = 'REJECTED'",
            name=op.f("ck_campus_issues_duplicate_is_rejected"),
        ),
        sa.CheckConstraint(
            "(status = 'RESOLVED') = (resolved_at IS NOT NULL)",
            name=op.f("ck_campus_issues_resolved_at_state"),
        ),
        sa.CheckConstraint(
            "reporter_reopen_count BETWEEN 0 AND 2",
            name=op.f("ck_campus_issues_reporter_reopens"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_campus_issues_version_positive")),
        sa.ForeignKeyConstraint(
            ["college_id", "reporter_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_campus_issues_reporter_membership",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "assignee_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_campus_issues_assignee_membership",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "duplicate_of_id"],
            ["campus_issues.college_id", "campus_issues.id"],
            name="fk_campus_issues_duplicate_of",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_campus_issues_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campus_issues")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_campus_issues_college_id_id")),
    )
    op.create_index(
        "ix_campus_issues_college_status_created",
        "campus_issues",
        ["college_id", "status", "created_at"],
    )
    op.create_index(
        "ix_campus_issues_reporter", "campus_issues", ["college_id", "reporter_membership_id"]
    )
    op.create_index(
        "ix_campus_issues_assignee", "campus_issues", ["college_id", "assignee_membership_id"]
    )

    op.create_table(
        "issue_updates",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("issue_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("actor_membership_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("is_internal", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _timestamp("created_at"),
        sa.CheckConstraint(
            "kind IN ('CREATED', 'STATUS', 'ASSIGNMENT', 'COMMENT')",
            name=op.f("ck_issue_updates_kind"),
        ),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({STATUSES})",
            name=op.f("ck_issue_updates_from_status"),
        ),
        sa.CheckConstraint(
            f"to_status IS NULL OR to_status IN ({STATUSES})",
            name=op.f("ck_issue_updates_to_status"),
        ),
        sa.CheckConstraint(
            "(kind = 'STATUS') = (from_status IS NOT NULL AND to_status IS NOT NULL)",
            name=op.f("ck_issue_updates_status_ends"),
        ),
        sa.CheckConstraint(
            "body IS NULL OR char_length(body) BETWEEN 1 AND 3000",
            name=op.f("ck_issue_updates_body_length"),
        ),
        sa.CheckConstraint(
            "kind <> 'COMMENT' OR body IS NOT NULL", name=op.f("ck_issue_updates_comment_has_body")
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "issue_id"],
            ["campus_issues.college_id", "campus_issues.id"],
            name="fk_issue_updates_issue",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "actor_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_issue_updates_actor_membership",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_issue_updates_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_issue_updates")),
    )
    op.create_index(
        "ix_issue_updates_issue_seq", "issue_updates", ["college_id", "issue_id", "seq"]
    )
    # ISSUE-005: the timeline is immutable. Rows are only ever inserted.
    op.execute(
        """
        CREATE FUNCTION issue_updates_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'issue_updates is append-only';
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER issue_updates_append_only BEFORE UPDATE OR DELETE ON issue_updates "
        "FOR EACH ROW EXECUTE FUNCTION issue_updates_append_only()"
    )


def downgrade() -> None:
    op.drop_table("issue_updates")  # drops the trigger with it
    op.execute("DROP FUNCTION issue_updates_append_only()")
    op.drop_table("campus_issues")
