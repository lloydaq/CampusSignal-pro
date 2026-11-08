"""Assessments and results (ACADEMIC-008, 009).

An assessment belongs to a section (name, kind, max score, date), with `published_at` / the
publisher set together and a `version` guarding score entry. A result per enrolled student:
a score of at least 0 or ABSENT (never both), unique per assessment, `revised_at` once a
published score changes; its foreign key to the enrollment blocks removing an enrollment that
has results (ACADEMIC-002: 409).

Downgrade drops both tables.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assessments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("max_score", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("held_on", sa.Date(), nullable=False),
        sa.Column("created_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_membership_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "kind IN ('QUIZ', 'ASSIGNMENT', 'LAB', 'MIDTERM', 'ENDTERM', 'OTHER')",
            name=op.f("ck_assessments_kind"),
        ),
        sa.CheckConstraint(
            "(published_at IS NULL) = (published_by_membership_id IS NULL)",
            name=op.f("ck_assessments_published"),
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 80", name=op.f("ck_assessments_name_length")
        ),
        sa.CheckConstraint("max_score > 0", name=op.f("ck_assessments_max_score_positive")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_assessments_version_positive")),
        sa.ForeignKeyConstraint(
            ["college_id", "created_by_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_assessments_created_by",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "published_by_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_assessments_published_by",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "section_id"],
            ["class_sections.college_id", "class_sections.id"],
            name="fk_assessments_section",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_assessments_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessments")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_assessments_college_id_id")),
    )
    op.create_index("ix_assessments_section_id", "assessments", ["section_id"], unique=False)
    op.create_table(
        "assessment_results",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("is_absent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("revised_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "(is_absent AND score IS NULL) OR (NOT is_absent AND score IS NOT NULL AND score >= 0)",
            name=op.f("ck_assessment_results_score_or_absent"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_assessment_results_version_positive")),
        sa.ForeignKeyConstraint(
            ["college_id", "assessment_id"],
            ["assessments.college_id", "assessments.id"],
            name="fk_assessment_results_assessment",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "enrollment_id"],
            ["enrollments.college_id", "enrollments.id"],
            name="fk_assessment_results_enrollment",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_assessment_results_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_results")),
        sa.UniqueConstraint(
            "assessment_id",
            "enrollment_id",
            name=op.f("uq_assessment_results_assessment_id_enrollment_id"),
        ),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_assessment_results_college_id_id")),
    )
    op.create_index(
        "ix_assessment_results_enrollment_id", "assessment_results", ["enrollment_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_assessment_results_enrollment_id", table_name="assessment_results")
    op.drop_table("assessment_results")
    op.drop_index("ix_assessments_section_id", table_name="assessments")
    op.drop_table("assessments")
