"""Community routes (architecture.md §11.1). The college comes from `Campus`; the service loads
the post or comment inside it and applies app/policies/community.py."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import Campus, Db, Now, no_store
from app.core.pagination import MAX_LIMIT, decode_cursor
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
    ReactionOut,
)
from app.services import community
from app.services.community import CommentView, Feed, PostView

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
