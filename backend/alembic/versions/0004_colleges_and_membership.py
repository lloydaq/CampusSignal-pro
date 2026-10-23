"""Colleges, departments, roster, memberships, role grants and invites.

Phase 3a (PRD ADMIN-001…003, MEMBER-001…011, DEPT-001/002, TENANT-004; architecture.md
§8.2, §9).

- College-scoped tables carry `college_id`, have UNIQUE (college_id, id), and reference each
  other through composite foreign keys (college_id, x_id), so a row can never point at another
  college's row. Composite constraint names are explicit (the generated ones would exceed
  PostgreSQL's 63-character limit).
- Partial unique indexes enforce one open request/membership per user and college, one ACTIVE
  membership per user (MEMBER-008) and one ACTIVE membership per roster entry (MEMBER-005).
- `role_grants`: DEPARTMENT_ADMIN must name a department and the other roles must not; the
  (membership, role, department) triple is unique with NULLS NOT DISTINCT (PostgreSQL 15+).
- Invite tokens are stored only as 32-byte SHA-256 digests.
- `audit_log.college_id` gains its foreign key to `colleges` (deferred from 0003).
- No functions are created, so there is nothing to REVOKE from PUBLIC (Rules R-2.22); Supabase
  API roles get no privileges on these tables through 0002's default-privilege changes.

Downgrade drops the tables (and their data) and the audit_log foreign key.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "colleges",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'ONBOARDING'"), nullable=False),
        sa.Column(
            "email_domains",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "attendance_edit_window_hours",
            sa.Integer(),
            server_default=sa.text("48"),
            nullable=False,
        ),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
            "slug ~ '^[a-z0-9]([a-z0-9-]{0,48}[a-z0-9])?$'", name=op.f("ck_colleges_slug_format")
        ),
        sa.CheckConstraint(
            "status IN ('ONBOARDING', 'ACTIVE', 'SUSPENDED')", name=op.f("ck_colleges_status")
        ),
        sa.CheckConstraint(
            "attendance_edit_window_hours BETWEEN 1 AND 720",
            name=op.f("ck_colleges_attendance_edit_window"),
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120", name=op.f("ck_colleges_name_length")
        ),
        sa.CheckConstraint(
            "char_length(timezone) BETWEEN 1 AND 64", name=op.f("ck_colleges_timezone_length")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_colleges")),
        sa.UniqueConstraint("slug", name=op.f("uq_colleges_slug")),
    )
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            "code ~ '^[A-Z0-9][A-Z0-9-]{0,15}$'", name=op.f("ck_departments_code_format")
        ),
        sa.CheckConstraint(
            "char_length(description) <= 2000", name=op.f("ck_departments_description_length")
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120", name=op.f("ck_departments_name_length")
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_departments_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_departments")),
        sa.UniqueConstraint("college_id", "code", name=op.f("uq_departments_college_id_code")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_departments_college_id_id")),
    )
    op.create_table(
        "invites",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "grants",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "jsonb_typeof(grants) = 'array'", name=op.f("ck_invites_grants_is_array")
        ),
        sa.CheckConstraint("kind IN ('FACULTY', 'STAFF')", name=op.f("ck_invites_kind")),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_invites_expires_after_created")
        ),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name=op.f("ck_invites_token_hash_length")
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"], ["users.id"], name=op.f("fk_invites_accepted_by_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_invites_college_id_colleges")
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"], ["users.id"], name=op.f("fk_invites_invited_by_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invites")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_invites_college_id_id")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_invites_token_hash")),
    )
    op.create_index("ix_invites_college_id_email", "invites", ["college_id", "email"], unique=False)
    op.create_table(
        "roster_entries",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("roll_number", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("program", sa.Text(), nullable=False),
        sa.Column("admission_year", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "admission_year BETWEEN 1900 AND 2200", name=op.f("ck_roster_entries_admission_year")
        ),
        sa.CheckConstraint(
            "char_length(full_name) BETWEEN 1 AND 120",
            name=op.f("ck_roster_entries_full_name_length"),
        ),
        sa.CheckConstraint(
            "char_length(program) BETWEEN 1 AND 120", name=op.f("ck_roster_entries_program_length")
        ),
        sa.CheckConstraint(
            "char_length(roll_number) BETWEEN 1 AND 40",
            name=op.f("ck_roster_entries_roll_number_length"),
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "department_id"],
            ["departments.college_id", "departments.id"],
            name="fk_roster_entries_department",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_roster_entries_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roster_entries")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_roster_entries_college_id_id")),
        sa.UniqueConstraint(
            "college_id", "roll_number", name=op.f("uq_roster_entries_college_id_roll_number")
        ),
    )
    op.create_table(
        "college_memberships",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("roster_entry_id", sa.Uuid(), nullable=True),
        sa.Column("verification_flag", sa.Text(), nullable=True),
        sa.Column("submitted_roll_number", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
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
            "kind IN ('STUDENT', 'FACULTY', 'STAFF')", name=op.f("ck_college_memberships_kind")
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'REJECTED', 'SUSPENDED', 'ENDED')",
            name=op.f("ck_college_memberships_status"),
        ),
        sa.CheckConstraint(
            "submitted_roll_number IS NULL OR verification_flag = 'NO_ROSTER_MATCH'",
            name=op.f("ck_college_memberships_roll_number_only_without_match"),
        ),
        sa.CheckConstraint(
            "verification_flag IN "
            "('NO_ROSTER_EMAIL', 'EMAIL_MISMATCH', 'ROSTER_CLAIMED', 'NO_ROSTER_MATCH')",
            name=op.f("ck_college_memberships_verification_flag"),
        ),
        sa.CheckConstraint(
            "decision_reason IS NULL OR char_length(decision_reason) BETWEEN 1 AND 500",
            name=op.f("ck_college_memberships_decision_reason_length"),
        ),
        sa.CheckConstraint(
            "submitted_roll_number IS NULL OR char_length(submitted_roll_number) BETWEEN 1 AND 40",
            name=op.f("ck_college_memberships_submitted_roll_number_length"),
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "department_id"],
            ["departments.college_id", "departments.id"],
            name="fk_college_memberships_department",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "roster_entry_id"],
            ["roster_entries.college_id", "roster_entries.id"],
            name="fk_college_memberships_roster_entry",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_college_memberships_college_id_colleges")
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name=op.f("fk_college_memberships_decided_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_college_memberships_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_college_memberships")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_college_memberships_college_id_id")),
    )
    op.create_index(
        "ix_college_memberships_college_id_status",
        "college_memberships",
        ["college_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_college_memberships_one_active_per_roster_entry",
        "college_memberships",
        ["roster_entry_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_college_memberships_one_active_per_user",
        "college_memberships",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_college_memberships_open_per_college",
        "college_memberships",
        ["user_id", "college_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'ACTIVE', 'SUSPENDED')"),
    )
    op.create_table(
        "role_grants",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("granted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(role = 'DEPARTMENT_ADMIN') = (department_id IS NOT NULL)",
            name=op.f("ck_role_grants_department_only_for_department_admin"),
        ),
        sa.CheckConstraint(
            "role IN ('COLLEGE_ADMIN', 'DEPARTMENT_ADMIN', 'ISSUE_COORDINATOR')",
            name=op.f("ck_role_grants_role"),
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "department_id"],
            ["departments.college_id", "departments.id"],
            name="fk_role_grants_department",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_role_grants_membership",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_role_grants_college_id_colleges")
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"],
            ["users.id"],
            name=op.f("fk_role_grants_granted_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_grants")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_role_grants_college_id_id")),
        sa.UniqueConstraint(
            "membership_id",
            "role",
            "department_id",
            name=op.f("uq_role_grants_membership_id_role_department_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        op.f("ix_role_grants_membership_id"), "role_grants", ["membership_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_audit_log_college_id_colleges"), "audit_log", "colleges", ["college_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_audit_log_college_id_colleges"), "audit_log", type_="foreignkey")
    op.drop_index(op.f("ix_role_grants_membership_id"), table_name="role_grants")
    op.drop_table("role_grants")
    op.drop_index(
        "uq_college_memberships_open_per_college",
        table_name="college_memberships",
        postgresql_where=sa.text("status IN ('PENDING', 'ACTIVE', 'SUSPENDED')"),
    )
    op.drop_index(
        "uq_college_memberships_one_active_per_user",
        table_name="college_memberships",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.drop_index(
        "uq_college_memberships_one_active_per_roster_entry",
        table_name="college_memberships",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.drop_index("ix_college_memberships_college_id_status", table_name="college_memberships")
    op.drop_table("college_memberships")
    op.drop_table("roster_entries")
    op.drop_index("ix_invites_college_id_email", table_name="invites")
    op.drop_table("invites")
    op.drop_table("departments")
    op.drop_table("colleges")
