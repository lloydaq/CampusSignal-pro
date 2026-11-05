"""Community: posts, comments and reactions (COMMUNITY-001…005, 008, 009).

Every route loads its post inside the caller's college and applies app/policies/community.py:
a post the caller may not read is a 404, so a department's posts don't reveal themselves to
other departments. Feeds filter in SQL by the same audience, and add up counts for a whole page
in a fixed number of queries (no query per post).
"""

import math
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import Select, delete, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.errors import Forbidden, NotFound, RateLimited, ValidationFailed
from app.core.pagination import Cursor, encode_cursor, newest_first, split_page
from app.models import (
    CollegeMembership,
    Comment,
    ContentStatus,
    Department,
    Post,
    PostVisibility,
    Reaction,
    User,
)
from app.policies.campus import CampusContext
from app.policies.community import (
    can_delete_comment,
    can_delete_post,
    can_edit_comment,
    can_edit_post,
    can_engage_post,
    can_moderate_post,
    can_post_with,
    can_read_comment,
    can_read_post,
    feed_audience,
    sees_hidden_in_feed,
)

# COMMUNITY-008: per member, in any hour.
POSTS_PER_HOUR = 10
COMMENTS_PER_HOUR = 60
RATE_WINDOW = timedelta(hours=1)


class Feed(StrEnum):
    COLLEGE = "college"
    DEPARTMENT = "department"


@dataclass(frozen=True)
class Author:
    name: str
    kind: str


@dataclass(frozen=True)
class PostView:
    post: Post
    author: Author
    department: Department | None
    reaction_count: int
    comment_count: int
    reacted: bool
    can_edit: bool
    can_delete: bool
    can_engage: bool


@dataclass(frozen=True)
class CommentView:
    comment: Comment
    author: Author
    can_edit: bool
    can_delete: bool


# --- shared ----------------------------------------------------------------------------------


def authors_of(
    db: Session, campus: CampusContext, membership_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, Author]:
    wanted = set(membership_ids)
    if not wanted:
        return {}
    rows = db.execute(
        select(CollegeMembership.id, User.display_name, CollegeMembership.kind)
        .join(User, User.id == CollegeMembership.user_id)
        .where(CollegeMembership.college_id == campus.college_id, CollegeMembership.id.in_(wanted))
    ).all()
    return {membership_id: Author(name, kind) for membership_id, name, kind in rows}


def _check_hourly_limit(
    db: Session,
    campus: CampusContext,
    created_at: InstrumentedAttribute[datetime],
    author: InstrumentedAttribute[uuid.UUID],
    college: InstrumentedAttribute[uuid.UUID],
    limit: int,
    now: datetime,
) -> None:
    """COMMUNITY-008, counted from the rows themselves (deleted ones too, so deleting doesn't
    free a slot): an exact rolling hour. The member's row is locked first, so two requests sent
    at once are counted one after the other."""
    db.execute(
        select(CollegeMembership.id)
        .where(CollegeMembership.id == campus.membership.id)
        .with_for_update()
    )
    recent = list(
        db.execute(
            select(created_at)
            .where(
                college == campus.college_id,
                author == campus.membership.id,
                created_at > now - RATE_WINDOW,
            )
            .order_by(created_at)
        ).scalars()
    )
    if len(recent) >= limit:
        frees_at = recent[len(recent) - limit] + RATE_WINDOW
        raise RateLimited(math.ceil((frees_at - now).total_seconds()))


# --- posts -----------------------------------------------------------------------------------


def load_post(
    db: Session, campus: CampusContext, post_id: uuid.UUID, *, lock: bool = False
) -> Post:
    """The post in this college that the caller may read, else NotFound."""
    query = select(Post).where(Post.college_id == campus.college_id, Post.id == post_id)
    post = db.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if post is None or not can_read_post(campus, post):
        raise NotFound()
    return post


def _views(db: Session, campus: CampusContext, posts: list[Post]) -> list[PostView]:
    """A page of posts with authors, departments and counts: five queries, however long the
    page (tests/integration/test_community.py counts them)."""
    if not posts:
        return []
    ids = [p.id for p in posts]
    authors = authors_of(db, campus, (p.author_membership_id for p in posts))
    department_ids = {p.department_id for p in posts if p.department_id}
    departments = (
        {
            d.id: d
            for d in db.execute(
                select(Department).where(
                    Department.college_id == campus.college_id, Department.id.in_(department_ids)
                )
            ).scalars()
        }
        if department_ids
        else {}
    )
    reactions: dict[uuid.UUID, int] = {
        post_id: count
        for post_id, count in db.execute(
            select(Reaction.post_id, func.count())
            .where(Reaction.college_id == campus.college_id, Reaction.post_id.in_(ids))
            .group_by(Reaction.post_id)
        ).all()
    }
    comments: dict[uuid.UUID, int] = {
        post_id: count
        for post_id, count in db.execute(
            select(Comment.post_id, func.count())
            .where(
                Comment.college_id == campus.college_id,
                Comment.post_id.in_(ids),
                Comment.deleted_at.is_(None),
                Comment.status == ContentStatus.VISIBLE,
            )
            .group_by(Comment.post_id)
        ).all()
    }
    mine = set(
        db.execute(
            select(Reaction.post_id).where(
                Reaction.college_id == campus.college_id,
                Reaction.post_id.in_(ids),
                Reaction.membership_id == campus.membership.id,
            )
        ).scalars()
    )
    return [
        PostView(
            post=p,
            author=authors[p.author_membership_id],
            department=departments.get(p.department_id) if p.department_id else None,
            reaction_count=reactions.get(p.id, 0),
            comment_count=comments.get(p.id, 0),
            reacted=p.id in mine,
            can_edit=can_edit_post(campus, p),
            can_delete=can_delete_post(campus, p),
            can_engage=can_engage_post(campus, p),
        )
        for p in posts
    ]


def get_post(db: Session, campus: CampusContext, post_id: uuid.UUID) -> PostView:
    return _views(db, campus, [load_post(db, campus, post_id)])[0]


def create_post(
    db: Session, campus: CampusContext, *, body: str, visibility: PostVisibility, now: datetime
) -> PostView:
    if not can_post_with(campus, visibility):
        raise ValidationFailed.field(
            "visibility", "You aren't in a department, so post to the whole college."
        )
    _check_hourly_limit(
        db, campus, Post.created_at, Post.author_membership_id, Post.college_id, POSTS_PER_HOUR, now
    )
    post = Post(
        college_id=campus.college_id,
        author_membership_id=campus.membership.id,
        visibility=visibility,
        department_id=campus.membership.department_id
        if visibility == PostVisibility.DEPARTMENT
        else None,
        body=body,
        created_at=now,
        updated_at=now,
    )
    db.add(post)
    db.commit()
    return get_post(db, campus, post.id)


def edit_post(
    db: Session, campus: CampusContext, post_id: uuid.UUID, *, body: str, now: datetime
) -> PostView:
    post = load_post(db, campus, post_id, lock=True)
    if not can_edit_post(campus, post):
        raise Forbidden()
    if body != post.body:
        post.body = body
        post.edited_at = now
        post.updated_at = now
    db.commit()
    return get_post(db, campus, post.id)


def delete_post(db: Session, campus: CampusContext, post_id: uuid.UUID, *, now: datetime) -> None:
    """COMMUNITY-005: soft. The post leaves every read; its row stays for reports about it."""
    post = load_post(db, campus, post_id, lock=True)
    if not can_delete_post(campus, post):
        raise Forbidden()
    post.deleted_at = now
    post.updated_at = now
    db.commit()


def _feed_department(
    db: Session, campus: CampusContext, department_id: uuid.UUID | None
) -> uuid.UUID:
    """The department whose feed is asked for: the one named, else the member's own. One the
    member can't read, or that isn't this college's, doesn't exist for them."""
    department = department_id or campus.membership.department_id
    if department is None or not feed_audience(campus).includes(department):
        raise NotFound()
    exists = db.execute(
        select(Department.id).where(
            Department.college_id == campus.college_id, Department.id == department
        )
    ).scalar_one_or_none()
    if exists is None:
        raise NotFound()
    return department


def list_feed(
    db: Session,
    campus: CampusContext,
    *,
    feed: Feed,
    department_id: uuid.UUID | None,
    cursor: Cursor | None,
    limit: int,
) -> tuple[list[PostView], str | None]:
    """COMMUNITY-002: newest first. Hidden posts only for whoever moderates the whole feed."""
    query: Select[Any] = select(Post).where(
        Post.college_id == campus.college_id, Post.deleted_at.is_(None)
    )
    if feed == Feed.COLLEGE:
        query = query.where(Post.visibility == PostVisibility.COLLEGE)
        hidden_too = sees_hidden_in_feed(campus, None)
    else:
        department = _feed_department(db, campus, department_id)
        query = query.where(
            Post.visibility == PostVisibility.DEPARTMENT, Post.department_id == department
        )
        hidden_too = sees_hidden_in_feed(campus, department)
    if not hidden_too:
        query = query.where(Post.status == ContentStatus.VISIBLE)
    rows = list(db.execute(newest_first(query, Post.created_at, Post.id, cursor, limit)).scalars())
    page, next_cursor = split_page(rows, limit, lambda p: (p.created_at, p.id))
    return _views(db, campus, page), next_cursor


# --- comments --------------------------------------------------------------------------------


def _comment_views(
    db: Session, campus: CampusContext, post: Post, comments: list[Comment]
) -> list[CommentView]:
    authors = authors_of(db, campus, (c.author_membership_id for c in comments))
    return [
        CommentView(
            comment=c,
            author=authors[c.author_membership_id],
            can_edit=can_edit_comment(campus, post, c),
            can_delete=can_delete_comment(campus, post, c),
        )
        for c in comments
    ]


def list_comments(
    db: Session,
    campus: CampusContext,
    post_id: uuid.UUID,
    *,
    cursor: Cursor | None,
    limit: int,
) -> tuple[list[CommentView], str | None]:
    """Oldest first (Design.md §5 screen 10), the same rules as reading one comment."""
    post = load_post(db, campus, post_id)
    query: Select[Any] = select(Comment).where(
        Comment.college_id == campus.college_id,
        Comment.post_id == post.id,
        Comment.deleted_at.is_(None),
    )
    if not can_moderate_post(campus, post):
        query = query.where(
            (Comment.status == ContentStatus.VISIBLE)
            | (Comment.author_membership_id == campus.membership.id)
        )
    if cursor is not None:
        query = query.where(
            tuple_(Comment.created_at, Comment.id) > tuple_(cursor.created_at, cursor.id)
        )
    rows = list(
        db.execute(
            query.order_by(Comment.created_at.asc(), Comment.id.asc()).limit(limit + 1)
        ).scalars()
    )
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if len(rows) > limit else None
    return _comment_views(db, campus, post, page), next_cursor


def add_comment(
    db: Session, campus: CampusContext, post_id: uuid.UUID, *, body: str, now: datetime
) -> CommentView:
    post = load_post(db, campus, post_id)
    if not can_engage_post(campus, post):
        raise Forbidden()
    _check_hourly_limit(
        db,
        campus,
        Comment.created_at,
        Comment.author_membership_id,
        Comment.college_id,
        COMMENTS_PER_HOUR,
        now,
    )
    comment = Comment(
        college_id=campus.college_id,
        post_id=post.id,
        author_membership_id=campus.membership.id,
        body=body,
        created_at=now,
        updated_at=now,
    )
    db.add(comment)
    db.commit()
    return _comment_views(db, campus, post, [comment])[0]


def load_comment(db: Session, campus: CampusContext, comment_id: uuid.UUID) -> tuple[Post, Comment]:
    """The comment in this college that the caller may read, with its post, else NotFound."""
    row = db.execute(
        select(Comment, Post)
        .join(Post, (Post.college_id == Comment.college_id) & (Post.id == Comment.post_id))
        .where(Comment.college_id == campus.college_id, Comment.id == comment_id)
        .with_for_update(of=Comment)
    ).one_or_none()
    if row is None or not can_read_comment(campus, row.Post, row.Comment):
        raise NotFound()
    return row.Post, row.Comment


def edit_comment(
    db: Session, campus: CampusContext, comment_id: uuid.UUID, *, body: str, now: datetime
) -> CommentView:
    post, comment = load_comment(db, campus, comment_id)
    if not can_edit_comment(campus, post, comment):
        raise Forbidden()
    if body != comment.body:
        comment.body = body
        comment.edited_at = now
        comment.updated_at = now
    db.commit()
    return _comment_views(db, campus, post, [comment])[0]


def delete_comment(
    db: Session, campus: CampusContext, comment_id: uuid.UUID, *, now: datetime
) -> None:
    post, comment = load_comment(db, campus, comment_id)
    if not can_delete_comment(campus, post, comment):
        raise Forbidden()
    comment.deleted_at = now
    comment.updated_at = now
    db.commit()


# --- reactions -------------------------------------------------------------------------------


def _reaction_count(db: Session, campus: CampusContext, post_id: uuid.UUID) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(Reaction)
            .where(Reaction.college_id == campus.college_id, Reaction.post_id == post_id)
        ).scalar_one()
    )


def react(db: Session, campus: CampusContext, post_id: uuid.UUID, *, now: datetime) -> int:
    """COMMUNITY-004: "Helpful" once per member; reacting again changes nothing (the unique
    constraint makes that a database rule, also for two requests at once)."""
    post = load_post(db, campus, post_id)
    if not can_engage_post(campus, post):
        raise Forbidden()
    db.execute(
        insert(Reaction)
        .values(
            college_id=campus.college_id,
            post_id=post.id,
            membership_id=campus.membership.id,
            created_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_reactions_post_member")
    )
    db.commit()
    return _reaction_count(db, campus, post.id)


def unreact(db: Session, campus: CampusContext, post_id: uuid.UUID) -> int:
    post = load_post(db, campus, post_id)
    db.execute(
        delete(Reaction).where(
            Reaction.college_id == campus.college_id,
            Reaction.post_id == post.id,
            Reaction.membership_id == campus.membership.id,
        )
    )
    db.commit()
    return _reaction_count(db, campus, post.id)
