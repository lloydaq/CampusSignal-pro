"""Notices (NOTICE-001…006, DEPT-003). Every route loads the notice inside the caller's
college, then applies the policies in app/policies/notices.py: a notice the caller may not
read is a 404 (so drafts and other departments' notices don't reveal themselves); one they may
read but not change is a 403. Lists filter with the same audiences the policies expose.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, case, func, literal, or_, select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.pagination import (
    RankedCursor,
    encode_ranked_cursor,
)
from app.models import (
    CollegeMembership,
    Department,
    MembershipStatus,
    Notice,
    NoticePriority,
    NoticeScope,
    NoticeStatus,
    Role,
    RoleGrant,
    User,
)
from app.policies.campus import CampusContext
from app.policies.notices import (
    DepartmentAudience,
    can_manage_notice,
    can_publish_in,
    can_publish_notices,
    can_read_notice,
    managed_audience,
    published_audience,
)
from app.policies.notifications import notice_notifies_members as notify_members
from app.repositories.scoped import get_in_college
from app.services import notifications
from app.services.audit import record_audit

ACTION_CREATED = "notice.created"
ACTION_PUBLISHED = "notice.published"
ACTION_UPDATED = "notice.updated"
ACTION_WITHDRAWN = "notice.withdrawn"
ACTION_NOTIFIED = "notice.notified"


@dataclass(frozen=True)
class NoticeView:
    notice: Notice
    department: Department | None
    author_name: str
    can_manage: bool

    def pinned(self, now: datetime) -> bool:
        return is_pinned(self.notice, now)

    def expired(self, now: datetime) -> bool:
        return is_expired(self.notice, now)


def is_expired(notice: Notice, now: datetime) -> bool:
    return notice.expires_at is not None and notice.expires_at <= now


def is_pinned(notice: Notice, now: datetime) -> bool:
    """NOTICE-005: URGENT, published and not expired."""
    return (
        notice.status == NoticeStatus.PUBLISHED
        and notice.priority == NoticePriority.URGENT
        and not is_expired(notice, now)
    )


# --- loading ---------------------------------------------------------------------------------


def _view(db: Session, campus: CampusContext, notice: Notice) -> NoticeView:
    department = (
        get_in_college(db, Department, campus.college_id, notice.department_id)
        if notice.department_id
        else None
    )
    author_name = db.execute(
        select(User.display_name)
        .join(CollegeMembership, CollegeMembership.user_id == User.id)
        .where(
            CollegeMembership.college_id == campus.college_id,
            CollegeMembership.id == notice.author_membership_id,
        )
    ).scalar_one()
    return NoticeView(notice, department, author_name, can_manage_notice(campus, notice))


def _load(db: Session, campus: CampusContext, notice_id: uuid.UUID, *, lock: bool) -> Notice:
    """The notice in this college that the caller may read, else NotFound."""
    query = select(Notice).where(Notice.college_id == campus.college_id, Notice.id == notice_id)
    notice = db.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if notice is None or not can_read_notice(campus, notice):
        raise NotFound()
    return notice


def _load_for_change(db: Session, campus: CampusContext, notice_id: uuid.UUID) -> Notice:
    notice = _load(db, campus, notice_id, lock=True)
    if not can_manage_notice(campus, notice):
        raise Forbidden()
    return notice


def get_notice(db: Session, campus: CampusContext, notice_id: uuid.UUID) -> NoticeView:
    return _view(db, campus, _load(db, campus, notice_id, lock=False))


# --- listing ---------------------------------------------------------------------------------


def _audience_clause(include_college: bool, departments: DepartmentAudience) -> ColumnElement[bool]:
    clauses: list[ColumnElement[bool]] = []
    if include_college:
        clauses.append(Notice.scope == NoticeScope.COLLEGE)
    department_clause: ColumnElement[bool] = and_(
        Notice.scope == NoticeScope.DEPARTMENT,
        literal(True)
        if departments.every_department
        else Notice.department_id.in_(departments.department_ids),
    )
    if departments.every_department or departments.department_ids:
        clauses.append(department_clause)
    return or_(*clauses) if clauses else literal(False)


def _pinned_rank(now: datetime) -> ColumnElement[int]:
    return case(
        (
            and_(
                Notice.status == NoticeStatus.PUBLISHED,
                Notice.priority == NoticePriority.URGENT,
                or_(Notice.expires_at.is_(None), Notice.expires_at > now),
            ),
            1,
        ),
        else_=0,
    )


def list_notices(
    db: Session,
    campus: CampusContext,
    *,
    status: NoticeStatus,
    past: bool,
    category: str | None,
    department_id: uuid.UUID | None,
    now: datetime,
    cursor: RankedCursor | None,
    limit: int,
) -> tuple[list[NoticeView], str | None]:
    if status == NoticeStatus.PUBLISHED:
        audience = _audience_clause(True, published_audience(campus))
    else:
        managed = managed_audience(campus)
        audience = _audience_clause(managed.include_college, managed.departments)
    rank = _pinned_rank(now)
    sort_time = func.coalesce(Notice.published_at, Notice.created_at)
    query: Select[Any] = select(Notice).where(
        Notice.college_id == campus.college_id, Notice.status == status, audience
    )
    if status == NoticeStatus.PUBLISHED:
        # NOTICE-004: expired notices leave the default list and live under "Past notices".
        expired = and_(Notice.expires_at.is_not(None), Notice.expires_at <= now)
        query = query.where(expired if past else ~expired)
    if category:
        query = query.where(Notice.category == category)
    if department_id:
        query = query.where(Notice.department_id == department_id)
    if cursor is not None:
        query = query.where(
            tuple_(rank, sort_time, Notice.id)
            < tuple_(literal(cursor.rank), literal(cursor.sort_time), literal(cursor.id))
        )
    rows = list(
        db.execute(
            query.order_by(rank.desc(), sort_time.desc(), Notice.id.desc()).limit(limit + 1)
        ).scalars()
    )
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = page[-1]
        next_cursor = encode_ranked_cursor(
            int(is_pinned(last, now)), last.published_at or last.created_at, last.id
        )
    departments = _departments(db, campus, page)
    return [
        NoticeView(
            n,
            departments.get(n.department_id) if n.department_id else None,
            "",
            can_manage_notice(campus, n),
        )
        for n in page
    ], next_cursor


def _departments(
    db: Session, campus: CampusContext, notices: list[Notice]
) -> dict[uuid.UUID, Department]:
    ids = {n.department_id for n in notices if n.department_id}
    if not ids:
        return {}
    rows = db.execute(
        select(Department).where(Department.college_id == campus.college_id, Department.id.in_(ids))
    ).scalars()
    return {d.id: d for d in rows}


# --- writing ---------------------------------------------------------------------------------


def _department_for(
    db: Session, campus: CampusContext, scope: str, department_id: uuid.UUID | None
) -> Department | None:
    """The target department of a new notice, after the checks that decide 403 / 404 / 422."""
    if not can_publish_notices(campus):
        raise Forbidden()
    if scope == NoticeScope.COLLEGE:
        if not can_publish_in(campus, scope, None):
            raise Forbidden()  # a department admin can't publish college-wide
        return None
    if department_id is None:  # the schema ties the two together; this is only a guard
        raise ValidationFailed.field("department_id", "Choose a department.")
    department = get_in_college(db, Department, campus.college_id, department_id)
    if not can_publish_in(campus, scope, department.id):
        raise NotFound()  # a department that isn't theirs
    if department.archived_at is not None:
        raise ValidationFailed.field("department_id", "This department is archived.")
    return department


def _check_expiry(expires_at: datetime | None, now: datetime) -> None:
    if expires_at is not None and expires_at <= now:
        raise ValidationFailed.field("expires_at", "Choose a time in the future.")


def _audit(
    db: Session,
    campus: CampusContext,
    action: str,
    notice: Notice,
    *,
    reason: str | None = None,
    **extra: Any,
) -> None:
    record_audit(
        db,
        action=action,
        actor_user_id=campus.user.id,
        college_id=campus.college_id,
        target_type="notice",
        target_id=str(notice.id),
        reason=reason,
        metadata={
            "scope": notice.scope,
            "department_id": str(notice.department_id) if notice.department_id else None,
            "priority": notice.priority,
            "category": notice.category,
            **extra,
        },
    )


def create_notice(
    db: Session,
    campus: CampusContext,
    *,
    title: str,
    body: str,
    category: str,
    priority: str,
    scope: str,
    department_id: uuid.UUID | None,
    expires_at: datetime | None,
    publish: bool,
    now: datetime,
) -> NoticeView:
    department = _department_for(db, campus, scope, department_id)
    _check_expiry(expires_at, now)
    notice = Notice(
        college_id=campus.college_id,
        department_id=department.id if department else None,
        author_membership_id=campus.membership.id,
        title=title,
        body=body,
        category=category,
        priority=priority,
        scope=scope,
        status=NoticeStatus.DRAFT,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    db.add(notice)
    db.flush()
    _audit(db, campus, ACTION_CREATED, notice)
    if publish:
        _publish(db, campus, notice, now)
    db.commit()
    return _view(db, campus, notice)


def _publish(db: Session, campus: CampusContext, notice: Notice, now: datetime) -> None:
    _check_expiry(notice.expires_at, now)
    notice.status = NoticeStatus.PUBLISHED
    notice.published_at = now
    notice.version += 1
    notice.updated_at = now
    db.flush()
    _audit(db, campus, ACTION_PUBLISHED, notice)
    if notify_members(notice):
        notified = notifications.notify_notice_published(db, notice, now)
        _audit(db, campus, ACTION_NOTIFIED, notice, notified=notified)


def publish_notice(
    db: Session, campus: CampusContext, notice_id: uuid.UUID, *, version: int, now: datetime
) -> NoticeView:
    notice = _load_for_change(db, campus, notice_id)
    _check_version(notice, version)
    if notice.status != NoticeStatus.DRAFT:
        raise Conflict("Only a draft can be published.", code="invalid_transition")
    _publish(db, campus, notice, now)
    db.commit()
    return _view(db, campus, notice)


def _check_version(notice: Notice, version: int) -> None:
    if notice.version != version:
        raise Conflict(
            "Someone else changed this notice. Reload it and try again.", code="version_conflict"
        )


def update_notice(
    db: Session,
    campus: CampusContext,
    notice_id: uuid.UUID,
    *,
    version: int,
    changes: dict[str, Any],
    now: datetime,
) -> NoticeView:
    notice = _load_for_change(db, campus, notice_id)
    _check_version(notice, version)
    if notice.status == NoticeStatus.WITHDRAWN:
        raise Conflict("A withdrawn notice can't be edited.", code="invalid_transition")
    if "expires_at" in changes:
        _check_expiry(changes["expires_at"], now)
    changed = [name for name, value in changes.items() if getattr(notice, name) != value]
    if changed:
        for name in changed:
            setattr(notice, name, changes[name])
        notice.version += 1
        notice.updated_at = now
        if notice.status == NoticeStatus.PUBLISHED:
            notice.edited_at = now  # NOTICE-006: readers see that it was updated
            _audit(db, campus, ACTION_UPDATED, notice, fields=sorted(changed))
        db.flush()
    db.commit()
    return _view(db, campus, notice)


def withdraw_notice(
    db: Session, campus: CampusContext, notice_id: uuid.UUID, *, reason: str, now: datetime
) -> NoticeView:
    notice = _load_for_change(db, campus, notice_id)
    if notice.status != NoticeStatus.PUBLISHED:
        raise Conflict("Only a published notice can be withdrawn.", code="invalid_transition")
    notice.status = NoticeStatus.WITHDRAWN
    notice.version += 1
    notice.updated_at = now
    db.flush()
    notifications.forget_notice(db, notice.id)
    _audit(db, campus, ACTION_WITHDRAWN, notice, reason=reason)
    db.commit()
    return _view(db, campus, notice)


# --- department pages (DEPT-003) -------------------------------------------------------------


def department_admin_names(
    db: Session, campus: CampusContext, department_id: uuid.UUID
) -> list[str]:
    """Names only (DEPT-003) of the department's current admins."""
    rows = db.execute(
        select(User.display_name)
        .join(CollegeMembership, CollegeMembership.user_id == User.id)
        .join(
            RoleGrant,
            and_(
                RoleGrant.college_id == CollegeMembership.college_id,
                RoleGrant.membership_id == CollegeMembership.id,
            ),
        )
        .where(
            CollegeMembership.college_id == campus.college_id,
            CollegeMembership.status == MembershipStatus.ACTIVE,
            RoleGrant.role == Role.DEPARTMENT_ADMIN,
            RoleGrant.department_id == department_id,
        )
        .distinct()
        .order_by(User.display_name)
    )
    return list(rows.scalars())
