"""Campus issues: reporting and reading (ISSUE-001, 003, 006, 007, 009).

Every route loads the issue inside the caller's college and applies app/policies/issues.py: an
issue the caller may not read is a 404, so other people's reports don't reveal themselves. Lists
filter by the same facts the policy uses (reporter = me, assignee = me, or the whole college for
someone who may see the queue).
"""

import math
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import ColumnElement, Select, case, literal, select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound, RateLimited
from app.core.pagination import RankedCursor, encode_ranked_cursor
from app.models import (
    CampusIssue,
    CollegeMembership,
    IssueStatus,
    IssueUpdate,
    IssueUpdateKind,
    User,
)
from app.policies.campus import CampusContext
from app.policies.issues import can_read_issue, can_see_internal_updates, can_see_queue
from app.services.audit import record_audit

ACTION_CREATED = "issue.created"

# ISSUE-007: five reports per member in any 24 hours.
DAILY_REPORTS = 5
REPORT_WINDOW = timedelta(hours=24)


class IssueScope(StrEnum):
    MINE = "mine"
    ASSIGNED = "assigned"
    QUEUE = "queue"


@dataclass(frozen=True)
class IssueView:
    issue: CampusIssue
    reporter_name: str
    assignee_name: str | None


@dataclass(frozen=True)
class UpdateView:
    update: IssueUpdate
    actor_name: str | None


@dataclass(frozen=True)
class DuplicateView:
    """The original of a duplicate. `readable`: whether the viewer may open it (ISSUE-006)."""

    original: CampusIssue
    readable: bool


@dataclass(frozen=True)
class IssueDetailView(IssueView):
    updates: list[UpdateView]
    duplicate_of: DuplicateView | None


# --- names -----------------------------------------------------------------------------------


def _names(
    db: Session, college_id: uuid.UUID, membership_ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    wanted = {m for m in membership_ids if m is not None}
    if not wanted:
        return {}
    rows = db.execute(
        select(CollegeMembership.id, User.display_name)
        .join(User, User.id == CollegeMembership.user_id)
        .where(CollegeMembership.college_id == college_id, CollegeMembership.id.in_(wanted))
    ).all()
    return {membership_id: name for membership_id, name in rows}


def _views(db: Session, campus: CampusContext, issues: list[CampusIssue]) -> list[IssueView]:
    names = _names(
        db,
        campus.college_id,
        [i.reporter_membership_id for i in issues] + [i.assignee_membership_id for i in issues],
    )
    return [
        IssueView(
            issue,
            names[issue.reporter_membership_id],
            names.get(issue.assignee_membership_id) if issue.assignee_membership_id else None,
        )
        for issue in issues
    ]


# --- reporting -------------------------------------------------------------------------------


def _check_report_limit(db: Session, campus: CampusContext, now: datetime) -> None:
    """ISSUE-007, counted from the reports themselves: an exact rolling window. The member's row
    is locked first, so two reports sent at once are counted one after the other."""
    db.execute(
        select(CollegeMembership.id)
        .where(CollegeMembership.id == campus.membership.id)
        .with_for_update()
    )
    recent = list(
        db.execute(
            select(CampusIssue.created_at)
            .where(
                CampusIssue.college_id == campus.college_id,
                CampusIssue.reporter_membership_id == campus.membership.id,
                CampusIssue.created_at > now - REPORT_WINDOW,
            )
            .order_by(CampusIssue.created_at)
        ).scalars()
    )
    if len(recent) >= DAILY_REPORTS:
        # A slot frees up when the oldest report that keeps the count at the limit leaves.
        frees_at = recent[len(recent) - DAILY_REPORTS] + REPORT_WINDOW
        raise RateLimited(math.ceil((frees_at - now).total_seconds()))


def create_issue(
    db: Session,
    campus: CampusContext,
    *,
    category: str,
    title: str,
    description: str,
    location: str,
    room: str | None,
    now: datetime,
) -> IssueDetailView:
    _check_report_limit(db, campus, now)
    issue = CampusIssue(
        college_id=campus.college_id,
        reporter_membership_id=campus.membership.id,
        category=category,
        title=title,
        description=description,
        location_text=location,
        room=room,
        status=IssueStatus.SUBMITTED,
        created_at=now,
        updated_at=now,
    )
    db.add(issue)
    db.flush()
    db.add(
        IssueUpdate(
            college_id=campus.college_id,
            issue_id=issue.id,
            actor_membership_id=campus.membership.id,
            kind=IssueUpdateKind.CREATED,
            created_at=now,
        )
    )
    # The report's words stay out of the audit log; the category says enough.
    record_audit(
        db,
        action=ACTION_CREATED,
        actor_user_id=campus.user.id,
        college_id=campus.college_id,
        target_type="issue",
        target_id=str(issue.id),
        metadata={"category": category},
    )
    db.commit()
    return get_issue(db, campus, issue.id)


# --- reading ---------------------------------------------------------------------------------


def load_issue(
    db: Session, campus: CampusContext, issue_id: uuid.UUID, *, lock: bool = False
) -> CampusIssue:
    """The issue in this college that the caller may read, else NotFound."""
    query = select(CampusIssue).where(
        CampusIssue.college_id == campus.college_id, CampusIssue.id == issue_id
    )
    issue = db.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if issue is None or not can_read_issue(campus, issue):
        raise NotFound()
    return issue


def get_issue(db: Session, campus: CampusContext, issue_id: uuid.UUID) -> IssueDetailView:
    issue = load_issue(db, campus, issue_id)
    query = select(IssueUpdate).where(
        IssueUpdate.college_id == campus.college_id, IssueUpdate.issue_id == issue.id
    )
    if not can_see_internal_updates(campus, issue):
        query = query.where(IssueUpdate.is_internal.is_(False))
    updates = list(db.execute(query.order_by(IssueUpdate.seq)).scalars())
    names = _names(
        db,
        campus.college_id,
        [issue.reporter_membership_id, issue.assignee_membership_id]
        + [u.actor_membership_id for u in updates],
    )
    duplicate = None
    if issue.duplicate_of_id is not None:
        original = db.execute(
            select(CampusIssue).where(
                CampusIssue.college_id == campus.college_id,
                CampusIssue.id == issue.duplicate_of_id,
            )
        ).scalar_one()
        duplicate = DuplicateView(original, can_read_issue(campus, original))
    return IssueDetailView(
        issue=issue,
        reporter_name=names[issue.reporter_membership_id],
        assignee_name=names.get(issue.assignee_membership_id)
        if issue.assignee_membership_id
        else None,
        updates=[
            UpdateView(u, names.get(u.actor_membership_id) if u.actor_membership_id else None)
            for u in updates
        ],
        duplicate_of=duplicate,
    )


# --- listing ---------------------------------------------------------------------------------


def _queue_rank() -> ColumnElement[int]:
    """ISSUE-009: unacknowledged issues first."""
    return case((CampusIssue.status == IssueStatus.SUBMITTED, 0), else_=1)


def list_issues(
    db: Session,
    campus: CampusContext,
    *,
    scope: IssueScope,
    status: IssueStatus | None,
    category: str | None,
    assignee_id: uuid.UUID | None,
    older_than_days: int | None,
    cursor: RankedCursor | None,
    limit: int,
    now: datetime,
) -> tuple[list[IssueView], str | None]:
    query: Select[Any] = select(CampusIssue).where(CampusIssue.college_id == campus.college_id)
    if scope == IssueScope.MINE:
        query = query.where(CampusIssue.reporter_membership_id == campus.membership.id)
    elif scope == IssueScope.ASSIGNED:
        query = query.where(CampusIssue.assignee_membership_id == campus.membership.id)
    elif not can_see_queue(campus):
        raise Forbidden()
    if status is not None:
        query = query.where(CampusIssue.status == status)
    if category:
        query = query.where(CampusIssue.category == category)
    if assignee_id is not None:
        query = query.where(CampusIssue.assignee_membership_id == assignee_id)
    if older_than_days is not None:
        query = query.where(CampusIssue.created_at <= now - timedelta(days=older_than_days))

    # The queue reads oldest-unacknowledged first; personal lists newest first.
    queue = scope == IssueScope.QUEUE
    rank: ColumnElement[int] = _queue_rank() if queue else literal(0)
    key = tuple_(rank, CampusIssue.created_at, CampusIssue.id)
    if cursor is not None:
        after = tuple_(literal(cursor.rank), literal(cursor.sort_time), literal(cursor.id))
        query = query.where(key > after if queue else key < after)
    order = (
        (rank.asc(), CampusIssue.created_at.asc(), CampusIssue.id.asc())
        if queue
        else (CampusIssue.created_at.desc(), CampusIssue.id.desc())
    )
    rows = list(db.execute(query.order_by(*order).limit(limit + 1)).scalars())
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = page[-1]
        last_rank = int(queue and last.status != IssueStatus.SUBMITTED)
        next_cursor = encode_ranked_cursor(last_rank, last.created_at, last.id)
    return _views(db, campus, page), next_cursor
