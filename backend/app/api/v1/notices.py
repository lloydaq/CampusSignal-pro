"""Notice routes (architecture.md §11.1). The college comes from `Campus`; the service loads
the notice inside it and applies app/policies/notices.py."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import Campus, Db, Now, no_store
from app.core.pagination import MAX_LIMIT, decode_ranked_cursor
from app.models import NoticeCategory, NoticeStatus
from app.schemas.notices import (
    NoticeCreate,
    NoticeDetail,
    NoticePage,
    NoticePublish,
    NoticeUpdate,
    NoticeWithdraw,
    detail,
    summary,
)
from app.services import notices
from app.services.notices import NoticeView

router = APIRouter(prefix="/campus/notices", tags=["notices"], dependencies=[Depends(no_store)])

NOTICE_PAGE_SIZE = 20  # NOTICE-005
Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
CursorParam = Annotated[str | None, Query(max_length=200)]


def _detail(view: NoticeView, now: Now) -> NoticeDetail:
    return detail(
        view.notice,
        view.department,
        view.author_name,
        pinned=view.pinned(now),
        expired=view.expired(now),
        can_manage=view.can_manage,
    )


@router.get("")
def list_notices(
    campus: Campus,
    db: Db,
    now: Now,
    status: NoticeStatus = NoticeStatus.PUBLISHED,
    past: Annotated[bool, Query(description="Expired notices instead of current ones")] = False,
    category: NoticeCategory | None = None,
    department_id: uuid.UUID | None = None,
    cursor: CursorParam = None,
    limit: Limit = NOTICE_PAGE_SIZE,
) -> NoticePage:
    views, next_cursor = notices.list_notices(
        db,
        campus,
        status=status,
        past=past,
        category=category,
        department_id=department_id,
        now=now,
        cursor=decode_ranked_cursor(cursor),
        limit=limit,
    )
    return NoticePage(
        items=[
            summary(
                v.notice,
                v.department,
                pinned=v.pinned(now),
                expired=v.expired(now),
                can_manage=v.can_manage,
            )
            for v in views
        ],
        next_cursor=next_cursor,
    )


@router.post("", status_code=201)
def create_notice(body: NoticeCreate, campus: Campus, db: Db, now: Now) -> NoticeDetail:
    view = notices.create_notice(
        db,
        campus,
        title=body.title,
        body=body.body,
        category=body.category,
        priority=body.priority,
        scope=body.scope,
        department_id=body.department_id,
        expires_at=body.expires_at,
        publish=body.publish,
        now=now,
    )
    return _detail(view, now)


@router.get("/{notice_id}")
def get_notice(notice_id: uuid.UUID, campus: Campus, db: Db, now: Now) -> NoticeDetail:
    return _detail(notices.get_notice(db, campus, notice_id), now)


@router.patch("/{notice_id}")
def update_notice(
    notice_id: uuid.UUID, body: NoticeUpdate, campus: Campus, db: Db, now: Now
) -> NoticeDetail:
    changes = {name: getattr(body, name) for name in body.model_fields_set - {"version"}}
    view = notices.update_notice(
        db, campus, notice_id, version=body.version, changes=changes, now=now
    )
    return _detail(view, now)


@router.post("/{notice_id}/publish")
def publish_notice(
    notice_id: uuid.UUID, body: NoticePublish, campus: Campus, db: Db, now: Now
) -> NoticeDetail:
    return _detail(
        notices.publish_notice(db, campus, notice_id, version=body.version, now=now), now
    )


@router.post("/{notice_id}/withdraw")
def withdraw_notice(
    notice_id: uuid.UUID, body: NoticeWithdraw, campus: Campus, db: Db, now: Now
) -> NoticeDetail:
    return _detail(notices.withdraw_notice(db, campus, notice_id, reason=body.reason, now=now), now)
