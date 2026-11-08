"""Attendance (ACADEMIC-005…007): sessions and per-student records.

One session per section, date and slot (1-12), with a `version` for optimistic edits. A record
per enrolled student (PRESENT, ABSENT, EXCUSED), unique per session; its foreign key to the
enrollment blocks removing an enrollment that has attendance (ACADEMIC-002: 409).

Downgrade drops both tables.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attendance_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("held_on", sa.Date(), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column("recorded_by_membership_id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("slot BETWEEN 1 AND 12", name=op.f("ck_attendance_sessions_slot")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_attendance_sessions_version_positive")),
        sa.ForeignKeyConstraint(
            ["college_id", "recorded_by_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_attendance_sessions_recorded_by",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "section_id"],
            ["class_sections.college_id", "class_sections.id"],
            name="fk_attendance_sessions_section",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_attendance_sessions_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attendance_sessions")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_attendance_sessions_college_id_id")),
        sa.UniqueConstraint(
            "section_id",
            "held_on",
            "slot",
            name=op.f("uq_attendance_sessions_section_id_held_on_slot"),
        ),
    )
    op.create_table(
        "attendance_records",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "status IN ('PRESENT', 'ABSENT', 'EXCUSED')", name=op.f("ck_attendance_records_status")
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "enrollment_id"],
            ["enrollments.college_id", "enrollments.id"],
            name="fk_attendance_records_enrollment",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "session_id"],
            ["attendance_sessions.college_id", "attendance_sessions.id"],
            name="fk_attendance_records_session",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_attendance_records_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attendance_records")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_attendance_records_college_id_id")),
        sa.UniqueConstraint(
            "session_id",
            "enrollment_id",
            name=op.f("uq_attendance_records_session_id_enrollment_id"),
        ),
    )
    op.create_index(
        "ix_attendance_records_enrollment_id", "attendance_records", ["enrollment_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_attendance_records_enrollment_id", table_name="attendance_records")
    op.drop_table("attendance_records")
    op.drop_table("attendance_sessions")
