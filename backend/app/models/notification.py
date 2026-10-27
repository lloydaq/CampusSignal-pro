"""In-app notifications (NOTIF-001…004, architecture.md §15).

A row belongs to one user. `college_id` is set when the notification is about a college the
user belongs to; it is NULL for things that follow the person (e.g. a rejected request). Rows
carry only a reference to the subject and a non-sensitive title: never scores or attendance
values (NOTIF-004)."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class NotificationType(StrEnum):
    NOTICE_PUBLISHED = "NOTICE_PUBLISHED"
    MEMBERSHIP_DECIDED = "MEMBERSHIP_DECIDED"
    ISSUE_STATUS_CHANGED = "ISSUE_STATUS_CHANGED"
    ISSUE_ASSIGNED = "ISSUE_ASSIGNED"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="title_length"),
        Index(
            "ix_notifications_user_created",
            "user_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
        Index(
            "ix_notifications_user_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
        # A person is told about a published notice once, however the fan-out is retried.
        Index(
            "uq_notifications_notice_published",
            "user_id",
            "subject_id",
            unique=True,
            postgresql_where=text("type = 'NOTICE_PUBLISHED'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    college_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("colleges.id"))
    type: Mapped[str] = mapped_column(Text)
    subject_type: Mapped[str] = mapped_column(Text)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
