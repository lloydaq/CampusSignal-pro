"""Official notices (NOTICE-001…007, architecture.md §8.2).

A notice belongs to one college and is either college-wide or for one department. The database
keeps that consistent (scope ⇔ department, state ⇔ published_at), and composite foreign keys
tie both the department and the author to the same college (TENANT-004)."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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


class NoticeScope(StrEnum):
    COLLEGE = "COLLEGE"
    DEPARTMENT = "DEPARTMENT"


class NoticeStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"


class NoticeCategory(StrEnum):
    ACADEMIC = "ACADEMIC"
    EXAMINATION = "EXAMINATION"
    ADMINISTRATIVE = "ADMINISTRATIVE"
    EVENT = "EVENT"
    FACILITIES = "FACILITIES"
    GENERAL = "GENERAL"


class NoticePriority(StrEnum):
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


def _in(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class Notice(Base):
    __tablename__ = "notices"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        ForeignKeyConstraint(
            ["college_id", "department_id"],
            ["departments.college_id", "departments.id"],
            name="fk_notices_department",
        ),
        ForeignKeyConstraint(
            ["college_id", "author_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_notices_author_membership",
        ),
        CheckConstraint(_in("scope", NoticeScope), name="scope"),
        CheckConstraint(_in("status", NoticeStatus), name="status"),
        CheckConstraint(_in("category", NoticeCategory), name="category"),
        CheckConstraint(_in("priority", NoticePriority), name="priority"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 150", name="title_length"),
        CheckConstraint("char_length(body) BETWEEN 1 AND 10000", name="body_length"),
        CheckConstraint(
            "(scope = 'DEPARTMENT') = (department_id IS NOT NULL)", name="scope_department"
        ),
        # DRAFT is the only state without a publication time.
        CheckConstraint("(status = 'DRAFT') = (published_at IS NULL)", name="published_at_state"),
        CheckConstraint(
            "expires_at IS NULL OR published_at IS NULL OR expires_at > published_at",
            name="expires_after_published",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index(
            "ix_notices_college_status_published",
            "college_id",
            "status",
            text("published_at DESC"),
            text("id DESC"),
        ),
        Index("ix_notices_college_department", "college_id", "department_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    author_membership_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text, server_default=text("'NORMAL'"))
    scope: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'DRAFT'"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Optimistic concurrency for edits (architecture.md §11.1: 409 on a stale version).
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
