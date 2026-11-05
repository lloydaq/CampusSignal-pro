"""Community routes (architecture.md §11.1). The college comes from `Campus`; the service loads
the post or comment inside it and applies app/policies/community.py."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import Campus, Db, Now, no_store
from app.core.pagination import MAX_LIMIT, decode_cursor
from app.models import ReportStatus
from app.schemas.campus import DepartmentRef
from app.schemas.community import (
    Author,
    CommentCreate,
    CommentEdit,
    CommentOut,
    CommentPage,
    PostCreate,
    PostEdit,
    PostOut,
    PostPage,
    QueueItemOut,
    QueuePage,
    ReactionOut,
    ReportCreate,
    ReportedContent,
    ReportOut,
    Resolve,
    ResolveOut,
)
from app.services import community, moderation
from app.services.community import CommentView, Feed, PostView
from app.services.moderation import QueueItem, Resolution

router = APIRouter(prefix="/campus", tags=["community"], dependencies=[Depends(no_store)])

FEED_PAGE_SIZE = 20  # COMMUNITY-002
COMMENT_PAGE_SIZE = 50
Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
CursorParam = Annotated[str | None, Query(max_length=200)]


def _post(view: PostView) -> PostOut:
    post = view.post
    return PostOut(
        id=post.id,
        body=post.body,
        visibility=post.visibility,
        department=DepartmentRef.from_department(view.department) if view.department else None,
        author=Author(name=view.author.name, kind=view.author.kind),
        status=post.status,
        hidden_reason=post.hidden_reason,
        edited_at=post.edited_at,
        created_at=post.created_at,
        reaction_count=view.reaction_count,
        comment_count=view.comment_count,
        reacted=view.reacted,
        can_edit=view.can_edit,
        can_delete=view.can_delete,
        can_engage=view.can_engage,
    )


def _comment(view: CommentView) -> CommentOut:
    comment = view.comment
    return CommentOut(
        id=comment.id,
        body=comment.body,
        author=Author(name=view.author.name, kind=view.author.kind),
        status=comment.status,
        hidden_reason=comment.hidden_reason,
        edited_at=comment.edited_at,
        created_at=comment.created_at,
        can_edit=view.can_edit,
        can_delete=view.can_delete,
    )


@router.get("/posts")
def list_posts(
    campus: Campus,
    db: Db,
    feed: Feed = Feed.COLLEGE,
    department_id: uuid.UUID | None = None,
    cursor: CursorParam = None,
    limit: Limit = FEED_PAGE_SIZE,
) -> PostPage:
    views, next_cursor = community.list_feed(
        db,
        campus,
        feed=feed,
        department_id=department_id,
        cursor=decode_cursor(cursor),
        limit=limit,
    )
    return PostPage(items=[_post(v) for v in views], next_cursor=next_cursor)


@router.post("/posts", status_code=201)
def create_post(body: PostCreate, campus: Campus, db: Db, now: Now) -> PostOut:
    return _post(
        community.create_post(db, campus, body=body.body, visibility=body.visibility, now=now)
    )


@router.get("/posts/{post_id}")
def get_post(post_id: uuid.UUID, campus: Campus, db: Db) -> PostOut:
    return _post(community.get_post(db, campus, post_id))


@router.patch("/posts/{post_id}")
def edit_post(post_id: uuid.UUID, body: PostEdit, campus: Campus, db: Db, now: Now) -> PostOut:
    return _post(community.edit_post(db, campus, post_id, body=body.body, now=now))


@router.delete("/posts/{post_id}", status_code=204)
def delete_post(post_id: uuid.UUID, campus: Campus, db: Db, now: Now) -> Response:
    community.delete_post(db, campus, post_id, now=now)
    return Response(status_code=204)


@router.get("/posts/{post_id}/comments")
def list_comments(
    post_id: uuid.UUID,
    campus: Campus,
    db: Db,
    cursor: CursorParam = None,
    limit: Limit = COMMENT_PAGE_SIZE,
) -> CommentPage:
    views, next_cursor = community.list_comments(
        db, campus, post_id, cursor=decode_cursor(cursor), limit=limit
    )
    return CommentPage(items=[_comment(v) for v in views], next_cursor=next_cursor)


@router.post("/posts/{post_id}/comments", status_code=201)
def add_comment(
    post_id: uuid.UUID, body: CommentCreate, campus: Campus, db: Db, now: Now
) -> CommentOut:
    return _comment(community.add_comment(db, campus, post_id, body=body.body, now=now))


@router.patch("/comments/{comment_id}")
def edit_comment(
    comment_id: uuid.UUID, body: CommentEdit, campus: Campus, db: Db, now: Now
) -> CommentOut:
    return _comment(community.edit_comment(db, campus, comment_id, body=body.body, now=now))


@router.delete("/comments/{comment_id}", status_code=204)
def delete_comment(comment_id: uuid.UUID, campus: Campus, db: Db, now: Now) -> Response:
    community.delete_comment(db, campus, comment_id, now=now)
    return Response(status_code=204)


@router.put("/posts/{post_id}/reaction")
def react(post_id: uuid.UUID, campus: Campus, db: Db, now: Now) -> ReactionOut:
    return ReactionOut(reacted=True, reaction_count=community.react(db, campus, post_id, now=now))


@router.delete("/posts/{post_id}/reaction")
def unreact(post_id: uuid.UUID, campus: Campus, db: Db) -> ReactionOut:
    return ReactionOut(reacted=False, reaction_count=community.unreact(db, campus, post_id))


# --- reports and moderation (COMMUNITY-006, 007) ---


def _queue_item(item: QueueItem) -> QueueItemOut:
    report, post, comment = item.report, item.post, item.comment
    return QueueItemOut(
        id=report.id,
        reason=report.reason,
        note=report.note,
        status=report.status,
        created_at=report.created_at,
        open_reports=item.open_reports,
        content=ReportedContent(
            type="comment" if comment else "post",
            post_id=post.id,
            comment_id=comment.id if comment else None,
            body=comment.body if comment else post.body,
            author=Author(name=item.author.name, kind=item.author.kind),
            visibility=post.visibility,
            department=DepartmentRef.from_department(item.department) if item.department else None,
            status=comment.status if comment else post.status,
        ),
    )


@router.post("/reports", status_code=201)
def report_content(body: ReportCreate, campus: Campus, db: Db, now: Now) -> ReportOut:
    report = moderation.report_content(
        db,
        campus,
        post_id=body.post_id,
        comment_id=body.comment_id,
        reason=body.reason,
        note=body.note,
        now=now,
    )
    return ReportOut(id=report.id, status=report.status)


@router.get("/moderation/reports")
def moderation_queue(
    campus: Campus,
    db: Db,
    status: ReportStatus = ReportStatus.OPEN,
    cursor: CursorParam = None,
    limit: Limit = FEED_PAGE_SIZE,
) -> QueuePage:
    items, next_cursor = moderation.moderation_queue(
        db, campus, status=status, cursor=decode_cursor(cursor), limit=limit
    )
    return QueuePage(items=[_queue_item(i) for i in items], next_cursor=next_cursor)


@router.post("/moderation/reports/{report_id}/resolve")
def resolve_report(
    report_id: uuid.UUID, body: Resolve, campus: Campus, db: Db, now: Now
) -> ResolveOut:
    closed = moderation.resolve_report(
        db,
        campus,
        report_id,
        resolution=Resolution(body.action),
        reason=body.reason.strip() if body.reason else None,
        now=now,
    )
    return ResolveOut(action=body.action, closed_reports=closed)
