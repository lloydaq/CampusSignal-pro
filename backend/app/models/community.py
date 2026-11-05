"""Community posts, comments and reactions (COMMUNITY-001…005, architecture.md §8).

A post belongs to one college and is visible to the whole college or to one department; its
author, its department, its comments and its reactions are all in the same college, which
composite foreign keys enforce (TENANT-004). Deleting is soft (`deleted_at`): a deleted post
or comment drops out of every read but stays referenceable, e.g. by a report about it.
`status` HIDDEN is set by moderators acting on a report (COMMUNITY-006, 007), with the reason
the author is shown."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PostVisibility(StrEnum):
    COLLEGE = "COLLEGE"
    DEPARTMENT = "DEPARTMENT"


class ContentStatus(StrEnum):
    VISIBLE = "VISIBLE"
    HIDDEN = "HIDDEN"


class ReportReason(StrEnum):
    HARASSMENT = "HARASSMENT"
    SPAM = "SPAM"
    MISINFORMATION = "MISINFORMATION"
    PERSONAL_INFORMATION = "PERSONAL_INFORMATION"
    OTHER = "OTHER"


class ReportStatus(StrEnum):
    OPEN = "OPEN"
    ACTIONED = "ACTIONED"  # the content was hidden
    DISMISSED = "DISMISSED"


def _in(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        ForeignKeyConstraint(
            ["college_id", "author_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_posts_author_membership",
        ),
        ForeignKeyConstraint(
            ["college_id", "department_id"],
            ["departments.college_id", "departments.id"],
            name="fk_posts_department",
        ),
        CheckConstraint(_in("visibility", PostVisibility), name="visibility"),
        CheckConstraint(_in("status", ContentStatus), name="status"),
        CheckConstraint(
            "(status = 'HIDDEN') = (hidden_reason IS NOT NULL AND hidden_at IS NOT NULL)",
            name="hidden_reason",
        ),
        # A department post names its department; a college post names none.
        CheckConstraint(
            "(visibility = 'DEPARTMENT') = (department_id IS NOT NULL)", name="department_scope"
        ),
        CheckConstraint("char_length(body) BETWEEN 1 AND 5000", name="body_length"),
        Index(
            "ix_posts_feed",
            "college_id",
            "visibility",
            "department_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
        Index("ix_posts_author_created", "college_id", "author_membership_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    author_membership_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    visibility: Mapped[str] = mapped_column(Text)
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'VISIBLE'"))
    # Why a moderator hid it, shown to its author (COMMUNITY-007). Migration 0011.
    hidden_reason: Mapped[str | None] = mapped_column(Text)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Comment(Base):
    """One level only (COMMUNITY-003): a comment belongs to a post, never to another comment."""

    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        ForeignKeyConstraint(
            ["college_id", "post_id"],
            ["posts.college_id", "posts.id"],
            name="fk_comments_post",
        ),
        ForeignKeyConstraint(
            ["college_id", "author_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_comments_author_membership",
        ),
        CheckConstraint(_in("status", ContentStatus), name="status"),
        CheckConstraint(
            "(status = 'HIDDEN') = (hidden_reason IS NOT NULL AND hidden_at IS NOT NULL)",
            name="hidden_reason",
        ),
        CheckConstraint("char_length(body) BETWEEN 1 AND 2000", name="body_length"),
        Index("ix_comments_post_created", "college_id", "post_id", "created_at", "id"),
        Index("ix_comments_author_created", "college_id", "author_membership_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    post_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    author_membership_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'VISIBLE'"))
    # Why a moderator hid it, shown to its author (COMMUNITY-007). Migration 0011.
    hidden_reason: Mapped[str | None] = mapped_column(Text)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Reaction(Base):
    """ "Helpful" (COMMUNITY-004). One per member per post is a database rule."""

    __tablename__ = "reactions"
    __table_args__ = (
        UniqueConstraint("post_id", "membership_id", name="uq_reactions_post_member"),
        ForeignKeyConstraint(
            ["college_id", "post_id"],
            ["posts.college_id", "posts.id"],
            name="fk_reactions_post",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["college_id", "membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_reactions_membership",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    post_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentReport(Base):
    """A member's report about a post or a comment (COMMUNITY-006). `comment_id` is set for a
    comment, and `post_id` is then the comment's post, so moderation rights (which follow the
    post) need no second lookup. One OPEN report per member per target is a database rule."""

    __tablename__ = "content_reports"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        ForeignKeyConstraint(
            ["college_id", "reporter_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_content_reports_reporter",
        ),
        ForeignKeyConstraint(
            ["college_id", "post_id"],
            ["posts.college_id", "posts.id"],
            name="fk_content_reports_post",
        ),
        ForeignKeyConstraint(
            ["college_id", "comment_id"],
            ["comments.college_id", "comments.id"],
            name="fk_content_reports_comment",
        ),
        ForeignKeyConstraint(
            ["college_id", "handled_by_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_content_reports_handled_by",
        ),
        CheckConstraint(_in("reason", ReportReason), name="reason"),
        CheckConstraint(_in("status", ReportStatus), name="status"),
        CheckConstraint("note IS NULL OR char_length(note) BETWEEN 1 AND 500", name="note_length"),
        # Open reports are unhandled; closed ones say who closed them and when.
        CheckConstraint(
            "(status = 'OPEN') = (handled_by_membership_id IS NULL AND handled_at IS NULL)",
            name="handled",
        ),
        Index(
            "uq_content_reports_open",
            "reporter_membership_id",
            "post_id",
            "comment_id",
            unique=True,
            postgresql_where=text("status = 'OPEN'"),
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_content_reports_queue", "college_id", "status", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    reporter_membership_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    post_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    comment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reason: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'OPEN'"))
    handled_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
