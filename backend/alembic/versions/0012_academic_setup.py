"""Academic setup (ACADEMIC-001…004): terms, subjects, sections, enrollments, timetable.

One current term per college (partial unique index). Subject codes are unique per college,
section names per (term, subject). Instructors and timetable entries go with their section;
enrollments don't (a section with enrollments can't be deleted). Timetable entries of one
section can't overlap on the same weekday: an exclusion constraint, which needs btree_gist
for the uuid and smallint equality parts.

Downgrade drops the tables and btree_gist.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public")
    op.create_table(
        "academic_terms",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
            "char_length(name) BETWEEN 1 AND 80", name=op.f("ck_academic_terms_name_length")
        ),
        sa.CheckConstraint("starts_on < ends_on", name=op.f("ck_academic_terms_dates_in_order")),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_academic_terms_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_terms")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_academic_terms_college_id_id")),
        sa.UniqueConstraint("college_id", "name", name=op.f("uq_academic_terms_college_id_name")),
    )
    op.create_index(
        "uq_academic_terms_one_current",
        "academic_terms",
        ["college_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_table(
        "subjects",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
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
            "code ~ '^[A-Z0-9][A-Z0-9-]{0,15}$'", name=op.f("ck_subjects_code_format")
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120", name=op.f("ck_subjects_name_length")
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "department_id"],
            ["departments.college_id", "departments.id"],
            name="fk_subjects_department",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_subjects_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subjects")),
        sa.UniqueConstraint("college_id", "code", name=op.f("uq_subjects_college_id_code")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_subjects_college_id_id")),
    )
    op.create_index(
        "ix_subjects_college_id_department_id",
        "subjects",
        ["college_id", "department_id"],
        unique=False,
    )
    op.create_table(
        "class_sections",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
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
            "char_length(name) BETWEEN 1 AND 40", name=op.f("ck_class_sections_name_length")
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "subject_id"],
            ["subjects.college_id", "subjects.id"],
            name="fk_class_sections_subject",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "term_id"],
            ["academic_terms.college_id", "academic_terms.id"],
            name="fk_class_sections_term",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_class_sections_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_class_sections")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_class_sections_college_id_id")),
        sa.UniqueConstraint(
            "term_id", "subject_id", "name", name=op.f("uq_class_sections_term_id_subject_id_name")
        ),
    )
    op.create_index("ix_class_sections_subject_id", "class_sections", ["subject_id"], unique=False)
    op.create_table(
        "enrollments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_enrollments_membership",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "section_id"],
            ["class_sections.college_id", "class_sections.id"],
            name="fk_enrollments_section",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_enrollments_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollments")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_enrollments_college_id_id")),
        sa.UniqueConstraint(
            "section_id", "membership_id", name=op.f("uq_enrollments_section_id_membership_id")
        ),
    )
    op.create_index("ix_enrollments_membership_id", "enrollments", ["membership_id"], unique=False)
    op.create_table(
        "section_instructors",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_section_instructors_membership",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "section_id"],
            ["class_sections.college_id", "class_sections.id"],
            name="fk_section_instructors_section",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_section_instructors_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_section_instructors")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_section_instructors_college_id_id")),
        sa.UniqueConstraint(
            "section_id",
            "membership_id",
            name=op.f("uq_section_instructors_section_id_membership_id"),
        ),
    )
    op.create_index(
        "ix_section_instructors_membership_id",
        "section_instructors",
        ["membership_id"],
        unique=False,
    )
    op.create_table(
        "timetable_entries",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("starts_at", sa.Time(), nullable=False),
        sa.Column("ends_at", sa.Time(), nullable=False),
        sa.Column("room", sa.Text(), nullable=False),
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
        postgresql.ExcludeConstraint(
            (sa.column("section_id"), "="),
            (sa.column("weekday"), "="),
            (sa.text("tsrange(DATE '2000-01-01' + starts_at, DATE '2000-01-01' + ends_at)"), "&&"),
            using="gist",
            name="ex_timetable_entries_no_overlap",
        ),
        sa.CheckConstraint(
            "char_length(room) BETWEEN 1 AND 60", name=op.f("ck_timetable_entries_room_length")
        ),
        sa.CheckConstraint("starts_at < ends_at", name=op.f("ck_timetable_entries_times_in_order")),
        sa.CheckConstraint("weekday BETWEEN 1 AND 7", name=op.f("ck_timetable_entries_weekday")),
        sa.ForeignKeyConstraint(
            ["college_id", "section_id"],
            ["class_sections.college_id", "class_sections.id"],
            name="fk_timetable_entries_section",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_timetable_entries_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_timetable_entries")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_timetable_entries_college_id_id")),
    )


def downgrade() -> None:
    op.drop_table("timetable_entries")
    op.drop_index("ix_section_instructors_membership_id", table_name="section_instructors")
    op.drop_table("section_instructors")
    op.drop_index("ix_enrollments_membership_id", table_name="enrollments")
    op.drop_table("enrollments")
    op.drop_index("ix_class_sections_subject_id", table_name="class_sections")
    op.drop_table("class_sections")
    op.drop_index("ix_subjects_college_id_department_id", table_name="subjects")
    op.drop_table("subjects")
    op.drop_index(
        "uq_academic_terms_one_current",
        table_name="academic_terms",
        postgresql_where=sa.text("is_current"),
    )
    op.drop_table("academic_terms")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
