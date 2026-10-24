"""Notification shapes (architecture.md §11.1). References and non-sensitive titles only
(NOTIF-004): the subject is a type and an id, never its content."""

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel

from app.models.notification import Notification


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    subject_type: str
    subject_id: uuid.UUID
    read: bool
    created_at: datetime

    @classmethod
    def from_notification(cls, notification: Notification) -> Self:
        return cls(
            id=notification.id,
            type=notification.type,
            title=notification.title,
            subject_type=notification.subject_type,
            subject_id=notification.subject_id,
            read=notification.read_at is not None,
            created_at=notification.created_at,
        )


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    next_cursor: str | None


class UnreadCount(BaseModel):
    unread: int


class MarkedRead(BaseModel):
    marked: int
