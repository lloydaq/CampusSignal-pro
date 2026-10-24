"""Joining a college by roll number and the approval queue (MEMBER-002…006, MEMBER-010).

The requester only ever learns "joined" (their verified email matched an unclaimed roster
entry) or the same "request sent" answer; why a request wasn't auto-activated is stored as a
verification flag for approvers (MEMBER-004). Roster entries are row-locked while a request or
an approval is decided, so two people can't end up holding one entry (MEMBER-005).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.pagination import Cursor, newest_first, split_page
from app.core.ratelimit import Limit
from app.models import (
    College,
    CollegeMembership,
    CollegeStatus,
    Department,
    MembershipKind,
    MembershipStatus,
    RosterEntry,
    VerificationFlag,
)
from app.models.user import User
from app.policies.campus import (
    CampusContext,
    administered_departments,
    can_view_directory,
    is_college_admin,
)
from app.policies.membership import (
    EMAIL_UNVERIFIED,
    can_review_request,
    classify_request,
    request_problem,
)
from app.services.audit import record_audit
from app.services.roster import ROLL_NUMBER

MEMBERSHIP_REQUESTS = Limit("membership:user", 5, timedelta(hours=24))  # MEMBER-010
ACTION_REQUESTED = "membership.requested"
ACTION_AUTO_ACTIVATED = "membership.auto_activated"
ACTION_APPROVED = "membership.approved"
ACTION_REJECTED = "membership.rejected"

_FORBIDDEN = {
    EMAIL_UNVERIFIED: "Verify your email first.",
    "platform_admin_cannot_join": (
        "Platform admin accounts can't join a college. Use a separate account."
    ),
}


def active_colleges(db: Session) -> list[College]:
    """The only cross-college data in the MVP: names and slugs of ACTIVE colleges (§9)."""
    return list(
        db.execute(
            select(College)
            .where(College.status == CollegeStatus.ACTIVE)
            .order_by(College.name)
            .limit(1000)
        ).scalars()
    )


def _claimed(db: Session, entry: RosterEntry, other_than: uuid.UUID | None = None) -> bool:
    query = exists().where(
        CollegeMembership.college_id == entry.college_id,
        CollegeMembership.roster_entry_id == entry.id,
        CollegeMembership.status == MembershipStatus.ACTIVE,
    )
    if other_than is not None:
        query = query.where(CollegeMembership.id != other_than)
    return bool(db.execute(select(query)).scalar())


def _lock_entry(db: Session, college_id: uuid.UUID, roll_number: str) -> RosterEntry | None:
    return db.execute(
        select(RosterEntry)
        .where(RosterEntry.college_id == college_id, RosterEntry.roll_number == roll_number)
        .with_for_update()
    ).scalar_one_or_none()


@dataclass(frozen=True)
class RequestResult:
    college: College
    membership: CollegeMembership
    activated: bool


def request_membership(
    db: Session, *, user: User, college_slug: str, roll_number: str, now: datetime
) -> RequestResult:
    problem = request_problem(user)
    if problem is not None:
        raise Forbidden(_FORBIDDEN[problem], code=problem)
    # Counted before anything else, so failed and malformed attempts can't probe for free.
    ratelimit.consume(db, MEMBERSHIP_REQUESTS, str(user.id), now)

    roll = roll_number.strip().upper()
    if not ROLL_NUMBER.match(roll):
        raise ValidationFailed.field(
            "roll_number", "Enter your roll number as it appears on your ID card."
        )
    college = db.execute(
        select(College).where(College.slug == college_slug, College.status == CollegeStatus.ACTIVE)
    ).scalar_one_or_none()
    if college is None:
        raise NotFound()
    for membership in db.execute(
        select(CollegeMembership).where(
            CollegeMembership.user_id == user.id,
            CollegeMembership.status.in_(
                (MembershipStatus.ACTIVE, MembershipStatus.PENDING, MembershipStatus.SUSPENDED)
            ),
        )
    ).scalars():
        if membership.status == MembershipStatus.ACTIVE:
            raise Conflict("You're already a member of a college.", code="already_member")
        if membership.status == MembershipStatus.PENDING:
            raise Conflict("You already have a request waiting for review.", code="request_pending")
        if membership.college_id == college.id:
            raise Conflict("Your membership at this college is suspended.", code="membership_open")

    entry = _lock_entry(db, college.id, roll)
    outcome = classify_request(user, entry, entry is not None and _claimed(db, entry))
    membership = CollegeMembership(
        user_id=user.id,
        college_id=college.id,
        kind=MembershipKind.STUDENT,
        status=MembershipStatus.ACTIVE if outcome.activate else MembershipStatus.PENDING,
        department_id=entry.department_id if entry else None,
        roster_entry_id=entry.id if entry else None,
        verification_flag=outcome.flag,
        submitted_roll_number=roll if entry is None else None,
        decided_at=now if outcome.activate else None,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(membership)
            db.flush()
    except IntegrityError:
        raise Conflict(
            "You already have a membership or a request.", code="request_pending"
        ) from None
    record_audit(
        db,
        action=ACTION_AUTO_ACTIVATED if outcome.activate else ACTION_REQUESTED,
        actor_user_id=user.id,
        college_id=college.id,
        target_type="membership",
        target_id=str(membership.id),
        metadata={"flag": outcome.flag},
    )
    db.commit()
    return RequestResult(college, membership, outcome.activate)


def my_requests(db: Session, user: User) -> list[tuple[CollegeMembership, College]]:
    rows = db.execute(
        select(CollegeMembership, College)
        .join(College, College.id == CollegeMembership.college_id)
        .where(
            CollegeMembership.user_id == user.id,
            CollegeMembership.kind == MembershipKind.STUDENT,
            CollegeMembership.status.in_((MembershipStatus.PENDING, MembershipStatus.REJECTED)),
        )
        .order_by(CollegeMembership.created_at.desc())
        .limit(20)
    ).all()
    return [(m, c) for m, c in rows]


# --- the approval queue --------------------------------------------------------------------


@dataclass(frozen=True)
class QueueRow:
    request: CollegeMembership
    user: User
    entry: RosterEntry | None
    department: Department | None


def review_queue(
    db: Session,
    campus: CampusContext,
    *,
    status: MembershipStatus,
    cursor: Cursor | None,
    limit: int,
) -> tuple[list[QueueRow], str | None]:
    if not can_view_directory(campus):  # college admins and department admins
        raise Forbidden()
    statement = (
        select(CollegeMembership, User, RosterEntry, Department)
        .join(User, User.id == CollegeMembership.user_id)
        .outerjoin(
            RosterEntry,
            (RosterEntry.college_id == CollegeMembership.college_id)
            & (RosterEntry.id == CollegeMembership.roster_entry_id),
        )
        .outerjoin(
            Department,
            (Department.college_id == CollegeMembership.college_id)
            & (Department.id == CollegeMembership.department_id),
        )
        .where(
            CollegeMembership.college_id == campus.college_id,
            CollegeMembership.kind == MembershipKind.STUDENT,
            CollegeMembership.status == status,
        )
    )
    if not is_college_admin(campus.grants):
        # Same rule as can_review_request, in SQL so pages stay full (TENANT-003).
        statement = statement.where(
            CollegeMembership.verification_flag != VerificationFlag.NO_ROSTER_MATCH,
            CollegeMembership.department_id.in_(administered_departments(campus.grants)),
        )
    rows = db.execute(
        newest_first(statement, CollegeMembership.created_at, CollegeMembership.id, cursor, limit)
    ).all()
    page, next_cursor = split_page(list(rows), limit, lambda r: (r[0].created_at, r[0].id))
    return [QueueRow(m, u, e, d) for m, u, e, d in page], next_cursor


def _load_request(db: Session, campus: CampusContext, request_id: uuid.UUID) -> CollegeMembership:
    request = db.execute(
        select(CollegeMembership)
        .where(
            CollegeMembership.id == request_id,
            CollegeMembership.college_id == campus.college_id,
            CollegeMembership.kind == MembershipKind.STUDENT,
            CollegeMembership.status.in_(
                (MembershipStatus.PENDING, MembershipStatus.REJECTED, MembershipStatus.ACTIVE)
            ),
        )
        .with_for_update()
    ).scalar_one_or_none()
    # Requests the reviewer may not see don't exist for them (404, TENANT-002).
    if request is None or not can_review_request(campus, request):
        raise NotFound()
    if request.status != MembershipStatus.PENDING:
        raise Conflict("This request was already decided.", code="already_decided")
    return request


def approve(
    db: Session, campus: CampusContext, request_id: uuid.UUID, now: datetime
) -> CollegeMembership:
    request = _load_request(db, campus, request_id)
    if request.roster_entry_id is not None:
        entry = db.execute(
            select(RosterEntry)
            .where(
                RosterEntry.college_id == campus.college_id,
                RosterEntry.id == request.roster_entry_id,
            )
            .with_for_update()
        ).scalar_one()
    else:
        # NO_ROSTER_MATCH: approvable once the college has added the roll number (MEMBER-006).
        found = _lock_entry(db, campus.college_id, request.submitted_roll_number or "")
        if found is None:
            raise Conflict(
                "Add this roll number to the roster first, or reject the request.",
                code="no_roster_entry",
            )
        entry = found
    if _claimed(db, entry, other_than=request.id):
        raise Conflict(
            "Another member holds this roster entry. End that membership first.",
            code="roster_claimed",
        )
    request.roster_entry_id = entry.id
    request.department_id = entry.department_id
    request.status = MembershipStatus.ACTIVE
    request.decided_by_user_id = campus.user.id
    request.decided_at = now
    request.updated_at = now
    record_audit(
        db,
        action=ACTION_APPROVED,
        actor_user_id=campus.user.id,
        college_id=campus.college_id,
        target_type="membership",
        target_id=str(request.id),
        metadata={"flag": request.verification_flag},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("The requester already holds a membership.", code="already_member") from None
    return request


def reject(
    db: Session, campus: CampusContext, request_id: uuid.UUID, reason: str, now: datetime
) -> CollegeMembership:
    request = _load_request(db, campus, request_id)
    request.status = MembershipStatus.REJECTED
    request.decision_reason = reason
    request.decided_by_user_id = campus.user.id
    request.decided_at = now
    request.updated_at = now
    record_audit(
        db,
        action=ACTION_REJECTED,
        actor_user_id=campus.user.id,
        college_id=campus.college_id,
        target_type="membership",
        target_id=str(request.id),
        reason=reason,
        metadata={"flag": request.verification_flag},
    )
    db.commit()
    return request
