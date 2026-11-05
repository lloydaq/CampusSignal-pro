"""Community moderation: reports, the queue, hiding and dismissing (COMMUNITY-006, 007).

A member reports a post or comment they can read; one OPEN report per member per target is a
database rule. Moderators (college admins for everything, department admins for their
departments' posts and the comments on them) see the open reports and either hide the content,
with a reason its author is told, or dismiss the reports. Either way every open report on that
content closes, and the action is audited. Reporters stay anonymous to moderators.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ColumnElement, and_, func, literal, or_, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound
from app.core.pagination import Cursor, encode_cursor
from app.models import (
    CollegeMembership,
    Comment,
    ContentReport,
    ContentStatus,
    Department,
    MembershipStatus,
    Post,
    PostVisibility,
    ReportReason,
    ReportStatus,
)
from app.models.notification import Notification, NotificationType
from app.policies.campus import CampusContext
from app.policies.community import (
    can_moderate_post,
    can_read_post,
    can_report,
    can_see_moderation_queue,
    moderation_audience,
)
from app.services.audit import record_audit
from app.services.community import Author, authors_of, load_comment, load_post

ACTION_HIDDEN = "community.content_hidden"
ACTION_DISMISSED = "community.reports_dismissed"


class Resolution(StrEnum):
    HIDE = "HIDE"
    DISMISS = "DISMISS"


@dataclass(frozen=True)
class QueueItem:
    report: ContentReport
    post: Post
    comment: Comment | None
    author: Author  # of the reported content
    department: Department | None
    open_reports: int  # on the same content, this one included


# --- reporting -------------------------------------------------------------------------------


def report_content(
    db: Session,
    campus: CampusContext,
    *,
    post_id: uuid.UUID | None,
    comment_id: uuid.UUID | None,
    reason: ReportReason,
    note: str | None,
    now: datetime,
) -> ContentReport:
    """Content the member can't read is a 404, like everywhere else."""
    if comment_id is not None:
        post, comment = load_comment(db, campus, comment_id)
    elif post_id is not None:
        post, comment = load_post(db, campus, post_id), None
    else:  # the schema requires exactly one of the two
        raise NotFound()
    if not can_report(campus, post, comment):
        raise Forbidden("You can't report this.")
    created = db.execute(
        insert(ContentReport)
        .values(
            college_id=campus.college_id,
            reporter_membership_id=campus.membership.id,
            post_id=post.id,
            comment_id=comment.id if comment else None,
            reason=reason,
            note=note,
            created_at=now,
        )
        .on_conflict_do_nothing(
            index_elements=["reporter_membership_id", "post_id", "comment_id"],
            index_where=text("status = 'OPEN'"),
        )
        .returning(ContentReport.id)
    ).scalar_one_or_none()
    if created is None:
        db.rollback()
        raise Conflict(
            "You've already reported this. A moderator will look at it.", code="already_reported"
        )
    db.commit()
    return db.execute(select(ContentReport).where(ContentReport.id == created)).scalar_one()


# --- the queue -------------------------------------------------------------------------------


def _audience_clause(campus: CampusContext) -> ColumnElement[bool]:
    audience = moderation_audience(campus)
    clauses: list[ColumnElement[bool]] = []
    if audience.include_college:
        clauses.append(Post.visibility == PostVisibility.COLLEGE)
    departments = audience.departments
    if departments.every_department:
        clauses.append(Post.visibility == PostVisibility.DEPARTMENT)
    elif departments.department_ids:
        clauses.append(
            and_(
                Post.visibility == PostVisibility.DEPARTMENT,
                Post.department_id.in_(departments.department_ids),
            )
        )
    return or_(*clauses) if clauses else literal(False)


def moderation_queue(
    db: Session,
    campus: CampusContext,
    *,
    status: ReportStatus,
    cursor: Cursor | None,
    limit: int,
) -> tuple[list[QueueItem], str | None]:
    """Oldest first. Reports on deleted content leave the queue (there's nothing to moderate)."""
    if not can_see_moderation_queue(campus):
        raise Forbidden()
    query = (
        select(ContentReport, Post, Comment)
        .join(
            Post, (Post.college_id == ContentReport.college_id) & (Post.id == ContentReport.post_id)
        )
        .outerjoin(
            Comment,
            (Comment.college_id == ContentReport.college_id)
            & (Comment.id == ContentReport.comment_id),
        )
        .where(
            ContentReport.college_id == campus.college_id,
            ContentReport.status == status,
            Post.deleted_at.is_(None),
            or_(ContentReport.comment_id.is_(None), Comment.deleted_at.is_(None)),
            _audience_clause(campus),
        )
    )
    if cursor is not None:
        query = query.where(
            tuple_(ContentReport.created_at, ContentReport.id)
            > tuple_(cursor.created_at, cursor.id)
        )
    rows = db.execute(
        query.order_by(ContentReport.created_at.asc(), ContentReport.id.asc()).limit(limit + 1)
    ).all()
    page = rows[:limit]
    next_cursor = (
        encode_cursor(page[-1].ContentReport.created_at, page[-1].ContentReport.id)
        if len(rows) > limit
        else None
    )
    if not page:
        return [], None

    authors = authors_of(
        db,
        campus,
        (
            r.Comment.author_membership_id if r.Comment else r.Post.author_membership_id
            for r in page
        ),
    )
    department_ids = {r.Post.department_id for r in page if r.Post.department_id}
    departments = {
        d.id: d
        for d in db.execute(
            select(Department).where(
                Department.college_id == campus.college_id, Department.id.in_(department_ids)
            )
        ).scalars()
    }
    # How many open reports each piece of content has (one query for the page).
    counts = {
        (post_id, comment_id): count
        for post_id, comment_id, count in db.execute(
            select(ContentReport.post_id, ContentReport.comment_id, func.count())
            .where(
                ContentReport.college_id == campus.college_id,
                ContentReport.status == ReportStatus.OPEN,
                ContentReport.post_id.in_({r.Post.id for r in page}),
            )
            .group_by(ContentReport.post_id, ContentReport.comment_id)
        ).all()
    }
    return [
        QueueItem(
            report=r.ContentReport,
            post=r.Post,
            comment=r.Comment,
            author=authors[
                r.Comment.author_membership_id if r.Comment else r.Post.author_membership_id
            ],
            department=departments.get(r.Post.department_id) if r.Post.department_id else None,
            open_reports=counts.get((r.Post.id, r.Comment.id if r.Comment else None), 0),
        )
        for r in page
    ], next_cursor


# --- resolving -------------------------------------------------------------------------------


def _close_open_reports(
    db: Session,
    campus: CampusContext,
    post: Post,
    comment: Comment | None,
    status: ReportStatus,
    now: datetime,
) -> int:
    target = (
        ContentReport.comment_id == comment.id
        if comment is not None
        else ContentReport.comment_id.is_(None)
    )
    result = db.execute(
        update(ContentReport)
        .where(
            ContentReport.college_id == campus.college_id,
            ContentReport.post_id == post.id,
            target,
            ContentReport.status == ReportStatus.OPEN,
        )
        .values(status=status, handled_by_membership_id=campus.membership.id, handled_at=now)
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


def _tell_author(
    db: Session, campus: CampusContext, post: Post, comment: Comment | None, now: datetime
) -> None:
    """COMMUNITY-007, NOTIF-002: the author learns their post or comment was hidden; the
    reason waits on the post itself (titles stay free of what anyone wrote)."""
    author_id = comment.author_membership_id if comment else post.author_membership_id
    author = db.execute(
        select(CollegeMembership).where(
            CollegeMembership.college_id == campus.college_id, CollegeMembership.id == author_id
        )
    ).scalar_one()
    if author.status != MembershipStatus.ACTIVE or author.id == campus.membership.id:
        return
    db.add(
        Notification(
            user_id=author.user_id,
            college_id=campus.college_id,
            type=NotificationType.CONTENT_HIDDEN,
            subject_type="POST",
            subject_id=post.id,
            title="A moderator hid your comment" if comment else "A moderator hid your post",
            created_at=now,
        )
    )


def resolve_report(
    db: Session,
    campus: CampusContext,
    report_id: uuid.UUID,
    *,
    resolution: Resolution,
    reason: str | None,
    now: datetime,
) -> int:
    """Hide the reported content (with a reason) or dismiss its reports. Returns how many open
    reports closed. A department admin acting on a college post gets 403 (US-10)."""
    report = db.execute(
        select(ContentReport)
        .where(ContentReport.college_id == campus.college_id, ContentReport.id == report_id)
        .with_for_update()
    ).scalar_one_or_none()
    if report is None:
        raise NotFound()
    post = db.execute(
        select(Post)
        .where(Post.college_id == campus.college_id, Post.id == report.post_id)
        .with_for_update()
    ).scalar_one()
    comment = (
        db.execute(
            select(Comment)
            .where(Comment.college_id == campus.college_id, Comment.id == report.comment_id)
            .with_for_update()
        ).scalar_one()
        if report.comment_id
        else None
    )
    if not can_moderate_post(campus, post):
        # Someone who can't even read the post doesn't learn the report exists.
        raise Forbidden() if can_read_post(campus, post) else NotFound()
    if report.status != ReportStatus.OPEN:
        raise Conflict("This report has already been handled.", code="already_resolved")
    target = comment or post
    target_type = "comment" if comment else "post"
    if resolution == Resolution.HIDE:
        if target.deleted_at is not None:
            raise Conflict("Its author already deleted it.", code="content_deleted")
        if target.status != ContentStatus.HIDDEN:
            target.status = ContentStatus.HIDDEN
            target.hidden_reason = reason
            target.hidden_at = now
            _tell_author(db, campus, post, comment, now)
        closed = _close_open_reports(db, campus, post, comment, ReportStatus.ACTIONED, now)
        action = ACTION_HIDDEN
    else:
        closed = _close_open_reports(db, campus, post, comment, ReportStatus.DISMISSED, now)
        action = ACTION_DISMISSED
    record_audit(
        db,
        action=action,
        actor_user_id=campus.user.id,
        college_id=campus.college_id,
        target_type=target_type,
        target_id=str(target.id),
        reason=reason,
        metadata={"reports": closed},
    )
    db.commit()
    return closed
