"""Notices (NOTICE-001…007).

One table. The database keeps a notice consistent: a department notice names a department of
the same college and a college notice names none; only a draft lacks a publication time; the
author is a membership of the same college. Drafts, published and withdrawn notices share the
table, and what readers may see is decided by the application (policies/notices.py).

Downgrade drops the table (and with it every notice).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notices",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("author_membership_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("priority", sa.Text(), server_default=sa.text("'NORMAL'"), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("scope IN ('COLLEGE', 'DEPARTMENT')", name=op.f("ck_notices_scope")),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'WITHDRAWN')", name=op.f("ck_notices_status")
        ),
        sa.CheckConstraint(
            "category IN ('ACADEMIC', 'EXAMINATION', 'ADMINISTRATIVE', 'EVENT', "
            "'FACILITIES', 'GENERAL')",
            name=op.f("ck_notices_category"),
        ),
        sa.CheckConstraint(
            "priority IN ('NORMAL', 'HIGH', 'URGENT')", name=op.f("ck_notices_priority")
        ),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 150", name=op.f("ck_notices_title_length")
        ),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 10000", name=op.f("ck_notices_body_length")
        ),
        sa.CheckConstraint(
            "(scope = 'DEPARTMENT') = (department_id IS NOT NULL)",
            name=op.f("ck_notices_scope_department"),
        ),
        sa.CheckConstraint(
            "(status = 'DRAFT') = (published_at IS NULL)",
            name=op.f("ck_notices_published_at_state"),
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR published_at IS NULL OR expires_at > published_at",
            name=op.f("ck_notices_expires_after_published"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_notices_version_positive")),
        sa.ForeignKeyConstraint(
            ["college_id", "department_id"],
            ["departments.college_id", "departments.id"],
            name="fk_notices_department",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "author_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_notices_author_membership",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_notices_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notices")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_notices_college_id_id")),
    )
    op.create_index(
        "ix_notices_college_status_published",
        "notices",
        [
            "college_id",
            "status",
            sa.literal_column("published_at DESC"),
            sa.literal_column("id DESC"),
        ],
    )
    op.create_index("ix_notices_college_department", "notices", ["college_id", "department_id"])


def downgrade() -> None:
    op.drop_table("notices")
