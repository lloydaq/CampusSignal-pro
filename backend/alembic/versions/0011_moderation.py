"""Moderation: content reports, and why hidden content was hidden (COMMUNITY-006, 007).

`content_reports` holds members' reports about a post or a comment (a comment's report also
names its post, so moderation rights follow the post). A member has at most one OPEN report
per target: a partial unique index with NULLS NOT DISTINCT (PostgreSQL 15+), so a post report
(no comment) is unique too. Closed reports say who closed them and when. Posts and comments
gain `hidden_reason` and `hidden_at`, set exactly when they are HIDDEN (no row can be hidden
before this migration, since nothing could hide one).

Downgrade drops the reports and the two columns.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_reports",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("reporter_membership_id", sa.Uuid(), nullable=False),
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("comment_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'OPEN'"), nullable=False),
        sa.Column("handled_by_membership_id", sa.Uuid(), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'OPEN') = (handled_by_membership_id IS NULL AND handled_at IS NULL)",
            name=op.f("ck_content_reports_handled"),
        ),
        sa.CheckConstraint(
            "reason IN ('HARASSMENT', 'SPAM', 'MISINFORMATION', 'PERSONAL_INFORMATION', 'OTHER')",
            name=op.f("ck_content_reports_reason"),
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'ACTIONED', 'DISMISSED')", name=op.f("ck_content_reports_status")
        ),
        sa.CheckConstraint(
            "note IS NULL OR char_length(note) BETWEEN 1 AND 500",
            name=op.f("ck_content_reports_note_length"),
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "comment_id"],
            ["comments.college_id", "comments.id"],
            name="fk_content_reports_comment",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "handled_by_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_content_reports_handled_by",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "post_id"],
            ["posts.college_id", "posts.id"],
            name="fk_content_reports_post",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "reporter_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_content_reports_reporter",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_content_reports_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_reports")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_content_reports_college_id_id")),
    )
    op.create_index(
        "ix_content_reports_queue",
        "content_reports",
        ["college_id", "status", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "uq_content_reports_open",
        "content_reports",
        ["reporter_membership_id", "post_id", "comment_id"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN'"),
        postgresql_nulls_not_distinct=True,
    )
    op.add_column("comments", sa.Column("hidden_reason", sa.Text(), nullable=True))
    op.add_column("comments", sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("posts", sa.Column("hidden_reason", sa.Text(), nullable=True))
    op.add_column("posts", sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True))
    for table in ("posts", "comments"):
        op.create_check_constraint(
            op.f(f"ck_{table}_hidden_reason"),
            table,
            "(status = 'HIDDEN') = (hidden_reason IS NOT NULL AND hidden_at IS NOT NULL)",
        )


def downgrade() -> None:
    for table in ("posts", "comments"):
        op.drop_constraint(op.f(f"ck_{table}_hidden_reason"), table, type_="check")
    op.drop_column("posts", "hidden_at")
    op.drop_column("posts", "hidden_reason")
    op.drop_column("comments", "hidden_at")
    op.drop_column("comments", "hidden_reason")
    op.drop_index(
        "uq_content_reports_open",
        table_name="content_reports",
        postgresql_where=sa.text("status = 'OPEN'"),
        postgresql_nulls_not_distinct=True,
    )
    op.drop_index("ix_content_reports_queue", table_name="content_reports")
    op.drop_table("content_reports")
