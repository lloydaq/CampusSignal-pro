"""Community posts, comments and reactions (COMMUNITY-001…005, architecture.md §8).

A post belongs to one college and is visible to the whole college or to one department; its
author, its department, its comments and its reactions are all in the same college, which
composite foreign keys enforce (TENANT-004). Deleting is soft (`deleted_at`): a deleted post
or comment drops out of every read but stays referenceable, e.g. by a report about it.
`status` HIDDEN is set by moderators (COMMUNITY-007, Phase 6b)."""

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
