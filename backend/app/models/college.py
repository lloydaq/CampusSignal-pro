import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# College-scoped tables (architecture.md §9, TENANT-004): every row carries college_id, every
# table has UNIQUE (college_id, id), and references between them are composite foreign keys
# (college_id, x_id) -> x (college_id, id), so a row of college A can never point at a row of
# college B, whatever the application code does. Composite constraint names are spelled out
# because the generated ones would pass PostgreSQL's 63-character limit.


class CollegeStatus(StrEnum):
    ONBOARDING = "ONBOARDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class MembershipKind(StrEnum):
    STUDENT = "STUDENT"
    FACULTY = "FACULTY"
    STAFF = "STAFF"


class MembershipStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"
    ENDED = "ENDED"


class VerificationFlag(StrEnum):
    """Why a student request wasn't auto-activated (MEMBER-004). Shown to approvers only."""

    NO_ROSTER_EMAIL = "NO_ROSTER_EMAIL"
    EMAIL_MISMATCH = "EMAIL_MISMATCH"
    ROSTER_CLAIMED = "ROSTER_CLAIMED"
    NO_ROSTER_MATCH = "NO_ROSTER_MATCH"


class Role(StrEnum):
    COLLEGE_ADMIN = "COLLEGE_ADMIN"
    DEPARTMENT_ADMIN = "DEPARTMENT_ADMIN"
    ISSUE_COORDINATOR = "ISSUE_COORDINATOR"


def _in(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class College(Base):
    """A tenant (ADMIN-001). Platform-wide table: it is what college_id refers to."""

    __tablename__ = "colleges"
    __table_args__ = (
        CheckConstraint(_in("status", CollegeStatus), name="status"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
        CheckConstraint("slug ~ '^[a-z0-9]([a-z0-9-]{0,48}[a-z0-9])?$'", name="slug_format"),
        CheckConstraint("char_length(timezone) BETWEEN 1 AND 64", name="timezone_length"),
        CheckConstraint(
            "attendance_edit_window_hours BETWEEN 1 AND 720", name="attendance_edit_window"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    timezone: Mapped[str] = mapped_column(Text)  # IANA name, validated by the service
    status: Mapped[str] = mapped_column(Text, server_default=text("'ONBOARDING'"))
    email_domains: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    attendance_edit_window_hours: Mapped[int] = mapped_column(Integer, server_default=text("48"))
    # Set at creation; drives "Demo data" labelling (architecture.md §8.2).
    is_demo: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        UniqueConstraint("college_id", "code"),
        CheckConstraint("code ~ '^[A-Z0-9][A-Z0-9-]{0,15}$'", name="code_format"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
        CheckConstraint("char_length(description) <= 2000", name="description_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, server_default=text("''"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RosterEntry(Base):
    """One student on a college's official roster (MEMBER-001)."""

    __tablename__ = "roster_entries"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        UniqueConstraint("college_id", "roll_number"),
        ForeignKeyConstraint(
            ["college_id", "department_id"],
            ["departments.college_id", "departments.id"],
            name="fk_roster_entries_department",
        ),
        CheckConstraint("char_length(roll_number) BETWEEN 1 AND 40", name="roll_number_length"),
        CheckConstraint("char_length(full_name) BETWEEN 1 AND 120", name="full_name_length"),
        CheckConstraint("char_length(program) BETWEEN 1 AND 120", name="program_length"),
        CheckConstraint("admission_year BETWEEN 1900 AND 2200", name="admission_year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    department_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    roll_number: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(CITEXT)
    program: Mapped[str] = mapped_column(Text)
    admission_year: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CollegeMembership(Base):
    """A user's tie to a college (MEMBER-002…011). Only ACTIVE grants college access."""

    __tablename__ = "college_memberships"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        ForeignKeyConstraint(
            ["college_id", "department_id"],
            ["departments.college_id", "departments.id"],
            name="fk_college_memberships_department",
        ),
        ForeignKeyConstraint(
            ["college_id", "roster_entry_id"],
            ["roster_entries.college_id", "roster_entries.id"],
            name="fk_college_memberships_roster_entry",
        ),
        CheckConstraint(_in("kind", MembershipKind), name="kind"),
        CheckConstraint(_in("status", MembershipStatus), name="status"),
        CheckConstraint(_in("verification_flag", VerificationFlag), name="verification_flag"),
        # The raw roll number is kept only when nothing on the roster matched (MEMBER-004).
        CheckConstraint(
            "submitted_roll_number IS NULL OR verification_flag = 'NO_ROSTER_MATCH'",
            name="roll_number_only_without_match",
        ),
        CheckConstraint(
            "submitted_roll_number IS NULL OR char_length(submitted_roll_number) BETWEEN 1 AND 40",
            name="submitted_roll_number_length",
        ),
        CheckConstraint(
            "decision_reason IS NULL OR char_length(decision_reason) BETWEEN 1 AND 500",
            name="decision_reason_length",
        ),
        # One open request or membership per college; one ACTIVE membership per user
        # (MEMBER-008); a roster entry backs at most one ACTIVE membership (MEMBER-005).
        Index(
            "uq_college_memberships_open_per_college",
            "user_id",
            "college_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'ACTIVE', 'SUSPENDED')"),
        ),
        Index(
            "uq_college_memberships_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "uq_college_memberships_one_active_per_roster_entry",
            "roster_entry_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_college_memberships_college_id_status", "college_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    roster_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    verification_flag: Mapped[str | None] = mapped_column(Text)
    submitted_roll_number: Mapped[str | None] = mapped_column(Text)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RoleGrant(Base):
    """An extra role on a membership (ADMIN-003, DEPT-002).

    DEPARTMENT_ADMIN names its department; the other roles never do.
    """

    __tablename__ = "role_grants"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        UniqueConstraint(
            "membership_id", "role", "department_id", postgresql_nulls_not_distinct=True
        ),
        ForeignKeyConstraint(
            ["college_id", "membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_role_grants_membership",
        ),
        ForeignKeyConstraint(
            ["college_id", "department_id"],
            ["departments.college_id", "departments.id"],
            name="fk_role_grants_department",
        ),
        CheckConstraint(_in("role", Role), name="role"),
        CheckConstraint(
            "(role = 'DEPARTMENT_ADMIN') = (department_id IS NOT NULL)",
            name="department_only_for_department_admin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    role: Mapped[str] = mapped_column(Text)
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invite(Base):
    """Single-use, email-bound invitation for faculty/staff and college admins (MEMBER-007,
    ADMIN-002). Only the SHA-256 digest of the token is stored."""

    __tablename__ = "invites"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        CheckConstraint("kind IN ('FACULTY', 'STAFF')", name="kind"),
        CheckConstraint("octet_length(token_hash) = 32", name="token_hash_length"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        CheckConstraint("jsonb_typeof(grants) = 'array'", name="grants_is_array"),
        Index("ix_invites_college_id_email", "college_id", "email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    email: Mapped[str] = mapped_column(CITEXT)
    kind: Mapped[str] = mapped_column(Text)
    # Roles granted on acceptance, e.g. [{"role": "COLLEGE_ADMIN"}].
    grants: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
