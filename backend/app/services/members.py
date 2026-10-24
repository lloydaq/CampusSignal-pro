"""Member directory, membership changes and role grants (ADMIN-003, DEPT-002, MEMBER-011).

Changes that could remove a college's last college admin lock the college row first, so two
admins acting at once can't both step down (Rules: row locks for contested updates).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.pagination import Cursor, newest_first, split_page
from app.models import (
    College,
    CollegeMembership,
    Department,
    MembershipKind,
    MembershipStatus,
    Role,
    RoleGrant,
    RosterEntry,
)
from app.models.user import User
from app.policies.campus import (
    CampusContext,
    administered_departments,
    can_change_membership_status,
    can_see_contact_details,
    can_view_directory,
    grant_problem,
    is_college_admin,
    leaves_no_college_admin,
    membership_change_needs_reason,
)
from app.repositories.scoped import get_in_college
from app.services.audit import record_audit
from app.services.departments import require_college_admin

ACTION_MEMBERSHIP = {
    MembershipStatus.SUSPENDED: "college.membership_suspended",
    MembershipStatus.ACTIVE: "college.membership_reactivated",
    MembershipStatus.ENDED: "college.membership_ended",
}
ACTION_DEPARTMENT_CHANGED = "college.membership_department_changed"
ACTION_ROLE_GRANTED = "college.role_granted"
ACTION_ROLE_REVOKED = "college.role_revoked"

_LAST_ADMIN = (
    "A college must keep at least one college admin. Make someone else a college admin first."
)


@dataclass(frozen=True)
class MemberRow:
    membership: CollegeMembership
    user: User
    department: Department | None
    roll_number: str | None
    grants: list[tuple[RoleGrant, Department | None]]
    show_contact: bool


# --- directory -----------------------------------------------------------------------------


def directory(
    db: Session,
    campus: CampusContext,
    *,
    query: str | None,
    kind: MembershipKind | None,
    status: MembershipStatus | None,
    cursor: Cursor | None,
    limit: int,
) -> tuple[list[MemberRow], str | None]:
    if not can_view_directory(campus):
        raise Forbidden()
    college_admin = is_college_admin(campus.grants)
    statement = (
        select(CollegeMembership, User, RosterEntry.roll_number)
        .join(User, User.id == CollegeMembership.user_id)
        .outerjoin(
            RosterEntry,
            (RosterEntry.college_id == CollegeMembership.college_id)
            & (RosterEntry.id == CollegeMembership.roster_entry_id),
        )
        .where(CollegeMembership.college_id == campus.college_id)
        .where(
            CollegeMembership.status == status
            if status
            else CollegeMembership.status.in_((MembershipStatus.ACTIVE, MembershipStatus.SUSPENDED))
        )
    )
    if not college_admin:
        # Department admins: their departments' students, and all faculty/staff (PRD §11).
        statement = statement.where(
            or_(
                CollegeMembership.kind != MembershipKind.STUDENT,
                CollegeMembership.department_id.in_(administered_departments(campus.grants)),
            )
        )
    if kind is not None:
        statement = statement.where(CollegeMembership.kind == kind)
    if query:
        matches = [User.display_name.icontains(query, autoescape=True)]
        if college_admin:  # contact fields are searchable only by those who may see them
            matches += [
                User.email.icontains(query, autoescape=True),
                RosterEntry.roll_number.icontains(query, autoescape=True),
            ]
        statement = statement.where(or_(*matches))
    rows = db.execute(
        newest_first(statement, CollegeMembership.created_at, CollegeMembership.id, cursor, limit)
    ).all()
    page, next_cursor = split_page(list(rows), limit, lambda r: (r[0].created_at, r[0].id))
    return _member_rows(db, campus, [(m, u, roll) for m, u, roll in page]), next_cursor


def _member_rows(
    db: Session, campus: CampusContext, rows: list[tuple[CollegeMembership, User, str | None]]
) -> list[MemberRow]:
    membership_ids = [m.id for m, _, _ in rows]
    grants = list(
        db.execute(
            select(RoleGrant)
            .where(
                RoleGrant.college_id == campus.college_id,
                RoleGrant.membership_id.in_(membership_ids),
            )
            .order_by(RoleGrant.role, RoleGrant.created_at)
        ).scalars()
    )
    departments = {
        d.id: d
        for d in db.execute(
            select(Department).where(Department.college_id == campus.college_id)
        ).scalars()
    }
    result = []
    for membership, user, roll in rows:
        show = can_see_contact_details(campus, membership)
        result.append(
            MemberRow(
                membership=membership,
                user=user,
                department=departments.get(membership.department_id)
                if membership.department_id
                else None,
                roll_number=roll if show else None,
                grants=[
                    (g, departments.get(g.department_id) if g.department_id else None)
                    for g in grants
                    if g.membership_id == membership.id
                ],
                show_contact=show,
            )
        )
    return result


def member_row(db: Session, campus: CampusContext, membership: CollegeMembership) -> MemberRow:
    user = db.execute(select(User).where(User.id == membership.user_id)).scalar_one()
    roll = None
    if membership.roster_entry_id is not None:
        roll = get_in_college(
            db, RosterEntry, campus.college_id, membership.roster_entry_id
        ).roll_number
    return _member_rows(db, campus, [(membership, user, roll)])[0]


# --- membership changes --------------------------------------------------------------------


def _lock_college(db: Session, campus: CampusContext) -> None:
    db.execute(select(College.id).where(College.id == campus.college_id).with_for_update())


def _other_active_admins(db: Session, campus: CampusContext, membership_id: uuid.UUID) -> int:
    return int(
        db.execute(
            select(func.count(func.distinct(CollegeMembership.id)))
            .join(
                RoleGrant,
                (RoleGrant.college_id == CollegeMembership.college_id)
                & (RoleGrant.membership_id == CollegeMembership.id),
            )
            .where(
                CollegeMembership.college_id == campus.college_id,
                CollegeMembership.status == MembershipStatus.ACTIVE,
                CollegeMembership.id != membership_id,
                RoleGrant.role == Role.COLLEGE_ADMIN,
            )
        ).scalar_one()
    )


def _is_active_admin(db: Session, campus: CampusContext, membership: CollegeMembership) -> bool:
    if membership.status != MembershipStatus.ACTIVE:
        return False
    return (
        db.execute(
            select(RoleGrant.id).where(
                RoleGrant.college_id == campus.college_id,
                RoleGrant.membership_id == membership.id,
                RoleGrant.role == Role.COLLEGE_ADMIN,
            )
        ).first()
        is not None
    )


def update_member(
    db: Session,
    campus: CampusContext,
    membership_id: uuid.UUID,
    *,
    department_id: uuid.UUID | None,
    status: str | None,
    reason: str | None,
    now: datetime,
) -> CollegeMembership:
    membership = get_in_college(db, CollegeMembership, campus.college_id, membership_id)
    if membership.status not in (
        MembershipStatus.ACTIVE,
        MembershipStatus.SUSPENDED,
        MembershipStatus.ENDED,
    ):
        raise NotFound()  # requests are handled in the approval queue, not here
    require_college_admin(campus)
    _lock_college(db, campus)
    db.refresh(membership)

    if department_id is not None and department_id != membership.department_id:
        department = get_in_college(db, Department, campus.college_id, department_id)
        if department.archived_at is not None:
            raise ValidationFailed.field("department_id", "This department is archived.")
        membership.department_id = department.id
        record_audit(
            db,
            action=ACTION_DEPARTMENT_CHANGED,
            actor_user_id=campus.user.id,
            college_id=campus.college_id,
            target_type="membership",
            target_id=str(membership.id),
            metadata={"department_id": str(department.id)},
        )

    if status is not None and status != membership.status:
        if not can_change_membership_status(membership.status, status):
            raise Conflict(
                f"A membership can't go from {membership.status} to {status}.",
                code="invalid_transition",
            )
        if membership_change_needs_reason(status) and not reason:
            raise ValidationFailed.field("reason", "Give a reason.")
        if leaves_no_college_admin(
            _other_active_admins(db, campus, membership.id),
            _is_active_admin(db, campus, membership),
        ):
            raise Conflict(_LAST_ADMIN, code="last_college_admin")
        record_audit(
            db,
            action=ACTION_MEMBERSHIP[MembershipStatus(status)],
            actor_user_id=campus.user.id,
            college_id=campus.college_id,
            target_type="membership",
            target_id=str(membership.id),
            reason=reason,
            metadata={"from": membership.status, "to": status},
        )
        membership.status = status
        membership.decided_by_user_id = campus.user.id
        membership.decided_at = now
    membership.updated_at = now
    db.commit()
    return membership


# --- roles ---------------------------------------------------------------------------------


def grant_role(
    db: Session,
    campus: CampusContext,
    membership_id: uuid.UUID,
    *,
    role: Role,
    department_id: uuid.UUID | None,
) -> tuple[RoleGrant, Department | None]:
    membership = get_in_college(db, CollegeMembership, campus.college_id, membership_id)
    require_college_admin(campus)
    department = None
    if department_id is not None:
        department = get_in_college(db, Department, campus.college_id, department_id)
        if department.archived_at is not None:
            raise ValidationFailed.field("department_id", "This department is archived.")
    problem = grant_problem(membership)
    if problem == "student_cannot_hold_roles":
        raise ValidationFailed("Students can't hold roles.", code=problem)
    if problem is not None:
        raise Conflict("Only active members can be given roles.", code=problem)
    grant = RoleGrant(
        college_id=campus.college_id,
        membership_id=membership.id,
        role=role,
        department_id=department.id if department else None,
        granted_by_user_id=campus.user.id,
    )
    try:
        with db.begin_nested():
            db.add(grant)
            db.flush()
    except IntegrityError:
        raise Conflict("This member already has this role.", code="grant_exists") from None
    record_audit(
        db,
        action=ACTION_ROLE_GRANTED,
        actor_user_id=campus.user.id,
        college_id=campus.college_id,
        target_type="membership",
        target_id=str(membership.id),
        metadata={"role": role, "department_id": str(department.id) if department else None},
    )
    db.commit()
    return grant, department


def revoke_role(
    db: Session, campus: CampusContext, membership_id: uuid.UUID, grant_id: uuid.UUID
) -> None:
    membership = get_in_college(db, CollegeMembership, campus.college_id, membership_id)
    grant = get_in_college(db, RoleGrant, campus.college_id, grant_id)
    if grant.membership_id != membership.id:
        raise NotFound()
    require_college_admin(campus)
    _lock_college(db, campus)
    if grant.role == Role.COLLEGE_ADMIN and leaves_no_college_admin(
        _other_active_admins(db, campus, membership.id), _is_active_admin(db, campus, membership)
    ):
        raise Conflict(_LAST_ADMIN, code="last_college_admin")
    record_audit(
        db,
        action=ACTION_ROLE_REVOKED,
        actor_user_id=campus.user.id,
        college_id=campus.college_id,
        target_type="membership",
        target_id=str(membership.id),
        metadata={
            "role": grant.role,
            "department_id": str(grant.department_id) if grant.department_id else None,
        },
    )
    db.delete(grant)
    db.commit()
