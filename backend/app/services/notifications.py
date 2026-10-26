"""In-app notifications (NOTIF-001…005, NOTICE-007, architecture.md §15).

Rows are written in the same transaction as the change that causes them, so a rolled-back
publish or decision leaves none behind and a committed one can't lose them. Reading goes
through the filter in `_visible`, the SQL form of policies/notifications.py.
"""

import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, and_, delete, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.pagination import Cursor, newest_first, split_page
from app.models import CollegeMembership, MembershipStatus, Notice, NoticePriority, NoticeScope
from app.models.notification import Notification, NotificationType
from app.policies.notifications import can_read_notification

TITLE_MAX = 200
NOTICE_LABEL = {NoticePriority.URGENT: "Urgent notice", NoticePriority.HIGH: "Important notice"}


def _title(text: str) -> str:
    return text if len(text) <= TITLE_MAX else text[: TITLE_MAX - 1].rstrip() + "…"


# --- creating ----------------------------------------------------------------------------------


def notify_notice_published(db: Session, notice: Notice, now: datetime) -> int:
    """One notification per ACTIVE member the notice is for (NOTICE-007): everyone in the
    college for a college notice, the department's members for a department notice. A single
    INSERT … SELECT, and a person already told about this notice is skipped."""
    title = _title(f"{NOTICE_LABEL[NoticePriority(notice.priority)]}: {notice.title}")
    recipients = select(
        CollegeMembership.user_id,
        CollegeMembership.college_id,
        literal(NotificationType.NOTICE_PUBLISHED.value),
        literal("NOTICE"),
        literal(notice.id),
        literal(title),
        literal(now),
    ).where(
        CollegeMembership.college_id == notice.college_id,
        CollegeMembership.status == MembershipStatus.ACTIVE,
    )
    if notice.scope == NoticeScope.DEPARTMENT:
        recipients = recipients.where(CollegeMembership.department_id == notice.department_id)
    statement = (
        insert(Notification)
        .from_select(
            ["user_id", "college_id", "type", "subject_type", "subject_id", "title", "created_at"],
            recipients,
        )
        .on_conflict_do_nothing()
        .returning(Notification.id)
    )
    return len(db.execute(statement).all())


def forget_notice(db: Session, notice_id: uuid.UUID) -> None:
    """A withdrawn notice must not linger in anyone's list with its title (NOTICE-003)."""
    db.execute(
        delete(Notification).where(
            Notification.type == NotificationType.NOTICE_PUBLISHED,
            Notification.subject_id == notice_id,
        )
    )


def notify_membership_decided(
    db: Session,
    *,
    user_id: uuid.UUID,
    request_id: uuid.UUID,
    college_id: uuid.UUID,
    college_name: str,
    approved: bool,
    now: datetime,
) -> None:
    """Tell the requester the college decided (NOTIF-002). An approval belongs to the college
    they just joined; a rejection follows the person, since they aren't a member of it."""
    db.add(
        Notification(
            user_id=user_id,
            college_id=college_id if approved else None,
            type=NotificationType.MEMBERSHIP_DECIDED,
            subject_type="MEMBERSHIP",
            subject_id=request_id,
            title=_title(
                f"You've joined {college_name}"
                if approved
                else f"Your request to join {college_name} wasn't approved"
            ),
            created_at=now,
        )
    )


def notify_issue(
    db: Session,
    *,
    user_id: uuid.UUID,
    college_id: uuid.UUID,
    issue_id: uuid.UUID,
    kind: NotificationType,
    title: str,
    now: datetime,
) -> None:
    """Tell the reporter their issue changed status, or a member an issue is now theirs
    (ISSUE-004, ISSUE-008). The title is the issue's own, which the recipient may read."""
    db.add(
        Notification(
            user_id=user_id,
            college_id=college_id,
            type=kind,
            subject_type="ISSUE",
            subject_id=issue_id,
            title=_title(title),
            created_at=now,
        )
    )


# --- reading -----------------------------------------------------------------------------------


def _visible(user_id: uuid.UUID, current_college: uuid.UUID | None) -> ColumnElement[bool]:
    follows_person: ColumnElement[bool] = Notification.college_id.is_(None)
    if current_college is None:
        return and_(Notification.user_id == user_id, follows_person)
    return and_(
        Notification.user_id == user_id,
        or_(follows_person, Notification.college_id == current_college),
    )


def list_notifications(
    db: Session,
    user_id: uuid.UUID,
    current_college: uuid.UUID | None,
    *,
    unread_only: bool,
    cursor: Cursor | None,
    limit: int,
) -> tuple[list[Notification], str | None]:
    query = select(Notification).where(_visible(user_id, current_college))
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    rows = list(
        db.execute(
            newest_first(query, Notification.created_at, Notification.id, cursor, limit)
        ).scalars()
    )
    return split_page(rows, limit, lambda n: (n.created_at, n.id))


def unread_count(db: Session, user_id: uuid.UUID, current_college: uuid.UUID | None) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(Notification)
            .where(_visible(user_id, current_college), Notification.read_at.is_(None))
        ).scalar_one()
    )


def mark_read(
    db: Session,
    user_id: uuid.UUID,
    current_college: uuid.UUID | None,
    notification_id: uuid.UUID,
    now: datetime,
) -> Notification:
    """Mark one read. Someone else's notification, or one from a college they no longer
    belong to, doesn't exist for them (404)."""
    notification = db.execute(
        select(Notification).where(Notification.id == notification_id).with_for_update()
    ).scalar_one_or_none()
    if notification is None or not can_read_notification(user_id, current_college, notification):
        raise NotFound()
    if notification.read_at is None:
        notification.read_at = now
    db.commit()
    return notification


def mark_all_read(
    db: Session, user_id: uuid.UUID, current_college: uuid.UUID | None, now: datetime
) -> int:
    result = db.execute(
        update(Notification)
        .where(_visible(user_id, current_college), Notification.read_at.is_(None))
        .values(read_at=now)
    )
    db.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]
