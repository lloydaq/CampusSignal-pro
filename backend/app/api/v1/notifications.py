"""The signed-in user's notifications (architecture.md §11.1). Not college routes: a person's
notifications follow them, so these start from the user and use the policy in
app/policies/notifications.py to decide which colleges' rows are visible."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import Auth, Db, Now, no_store
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, decode_cursor
from app.policies.notifications import current_college_id
from app.repositories.memberships import active_membership
from app.schemas.notifications import (
    MarkedRead,
    NotificationOut,
    NotificationPage,
    UnreadCount,
)
from app.services import notifications

router = APIRouter(
    prefix="/me/notifications", tags=["notifications"], dependencies=[Depends(no_store)]
)

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
CursorParam = Annotated[str | None, Query(max_length=200)]


def _college(auth: Auth, db: Db) -> uuid.UUID | None:
    active = active_membership(db, auth.user.id)
    return current_college_id(active[0] if active else None)


@router.get("")
def list_notifications(
    auth: Auth,
    db: Db,
    unread: bool = False,
    cursor: CursorParam = None,
    limit: Limit = DEFAULT_LIMIT,
) -> NotificationPage:
    items, next_cursor = notifications.list_notifications(
        db,
        auth.user.id,
        _college(auth, db),
        unread_only=unread,
        cursor=decode_cursor(cursor),
        limit=limit,
    )
    return NotificationPage(
        items=[NotificationOut.from_notification(n) for n in items], next_cursor=next_cursor
    )


@router.get("/unread-count")
def unread_count(auth: Auth, db: Db) -> UnreadCount:
    return UnreadCount(unread=notifications.unread_count(db, auth.user.id, _college(auth, db)))


@router.post("/read-all")
def read_all(auth: Auth, db: Db, now: Now) -> MarkedRead:
    return MarkedRead(marked=notifications.mark_all_read(db, auth.user.id, _college(auth, db), now))


@router.post("/{notification_id}/read")
def read_one(notification_id: uuid.UUID, auth: Auth, db: Db, now: Now) -> NotificationOut:
    return NotificationOut.from_notification(
        notifications.mark_read(db, auth.user.id, _college(auth, db), notification_id, now)
    )
