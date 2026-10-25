"""Campus issues (ISSUE-001…009, architecture.md §7.1 and §8).

An issue belongs to one college; its reporter, its assignee and the issue it duplicates are all
in the same college, which composite foreign keys enforce (TENANT-004). Every change leaves an
`issue_updates` row, and those rows are append-only: migration 0008 adds a trigger that refuses
UPDATE and DELETE on them (ISSUE-005: immutable)."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class IssueStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class IssueCategory(StrEnum):
    CLASSROOM_EQUIPMENT = "CLASSROOM_EQUIPMENT"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    WATER_SANITATION = "WATER_SANITATION"
    ELECTRICAL = "ELECTRICAL"
    NETWORK = "NETWORK"
    LIBRARY = "LIBRARY"
    LABORATORY = "LABORATORY"
    OTHER = "OTHER"


class IssueUpdateKind(StrEnum):
    CREATED = "CREATED"
    STATUS = "STATUS"
    ASSIGNMENT = "ASSIGNMENT"
    COMMENT = "COMMENT"


def _in(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class CampusIssue(Base):
    __tablename__ = "campus_issues"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        ForeignKeyConstraint(
            ["college_id", "reporter_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_campus_issues_reporter_membership",
        ),
        ForeignKeyConstraint(
            ["college_id", "assignee_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_campus_issues_assignee_membership",
        ),
        ForeignKeyConstraint(
            ["college_id", "duplicate_of_id"],
            ["campus_issues.college_id", "campus_issues.id"],
            name="fk_campus_issues_duplicate_of",
        ),
        CheckConstraint(_in("status", IssueStatus), name="status"),
        CheckConstraint(_in("category", IssueCategory), name="category"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 120", name="title_length"),
        CheckConstraint("char_length(description) BETWEEN 1 AND 3000", name="description_length"),
        CheckConstraint("char_length(location_text) BETWEEN 1 AND 200", name="location_length"),
        CheckConstraint("room IS NULL OR char_length(room) BETWEEN 1 AND 100", name="room_length"),
        CheckConstraint(
            "duplicate_of_id IS NULL OR duplicate_of_id <> id", name="not_own_duplicate"
        ),
        # A duplicate is always a rejected issue (ISSUE-006).
        CheckConstraint(
            "duplicate_of_id IS NULL OR status = 'REJECTED'", name="duplicate_is_rejected"
        ),
        CheckConstraint(
            "(status = 'RESOLVED') = (resolved_at IS NOT NULL)", name="resolved_at_state"
        ),
        CheckConstraint("reporter_reopen_count BETWEEN 0 AND 2", name="reporter_reopens"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_campus_issues_college_status_created", "college_id", "status", "created_at"),
        Index("ix_campus_issues_reporter", "college_id", "reporter_membership_id"),
        Index("ix_campus_issues_assignee", "college_id", "assignee_membership_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    reporter_membership_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    category: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    location_text: Mapped[str] = mapped_column(Text)
    room: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'SUBMITTED'"))
    assignee_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reporter_reopen_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Optimistic concurrency for transitions (architecture.md §11.1: 409 on a stale version).
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IssueUpdate(Base):
    """One entry in an issue's timeline (ISSUE-005). `actor_membership_id` is NULL only for
    changes made by the system."""

    __tablename__ = "issue_updates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["college_id", "issue_id"],
            ["campus_issues.college_id", "campus_issues.id"],
            name="fk_issue_updates_issue",
        ),
        ForeignKeyConstraint(
            ["college_id", "actor_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_issue_updates_actor_membership",
        ),
        CheckConstraint(_in("kind", IssueUpdateKind), name="kind"),
        CheckConstraint(
            f"from_status IS NULL OR {_in('from_status', IssueStatus)}", name="from_status"
        ),
        CheckConstraint(f"to_status IS NULL OR {_in('to_status', IssueStatus)}", name="to_status"),
        # A status change names both ends; nothing else names either.
        CheckConstraint(
            "(kind = 'STATUS') = (from_status IS NOT NULL AND to_status IS NOT NULL)",
            name="status_ends",
        ),
        CheckConstraint("body IS NULL OR char_length(body) BETWEEN 1 AND 3000", name="body_length"),
        CheckConstraint("kind <> 'COMMENT' OR body IS NOT NULL", name="comment_has_body"),
        Index("ix_issue_updates_issue_seq", "college_id", "issue_id", "seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    issue_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # Timeline order: several rows can share a timestamp (one request writes a status change and
    # its note), so order by this instead.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
    actor_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(Text)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    is_internal: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
