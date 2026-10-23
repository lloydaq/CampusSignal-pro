"""Membership lookups for the session and the campus context. These start from the user, not
from a college: they are how the acting college is found in the first place (TENANT-001)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import (
    College,
    CollegeMembership,
    Department,
    MembershipKind,
    MembershipStatus,
    Role,
    RoleGrant,
)

# Open memberships are shown on /me; REJECTED and ENDED ones are history.
_OPEN = (MembershipStatus.PENDING, MembershipStatus.ACTIVE, MembershipStatus.SUSPENDED)


@dataclass(frozen=True)
class MembershipView:
    membership: CollegeMembership
    college: College
    department: Department | None
    grants: tuple[RoleGrant, ...]
    grant_departments: dict[uuid.UUID, Department]


def grants_of(db: Session, membership: CollegeMembership) -> tuple[RoleGrant, ...]:
    rows = db.execute(
        select(RoleGrant)
        .where(
            RoleGrant.college_id == membership.college_id,
            RoleGrant.membership_id == membership.id,
        )
        .order_by(RoleGrant.role, RoleGrant.created_at)
    ).scalars()
    return tuple(rows)


def active_membership(db: Session, user_id: uuid.UUID) -> tuple[CollegeMembership, College] | None:
    """The user's single ACTIVE membership (MEMBER-008) and its college, whatever the college's
    status (the caller decides what an inactive college means)."""
    row = db.execute(
        select(CollegeMembership, College)
        .join(College, College.id == CollegeMembership.college_id)
        .where(
            CollegeMembership.user_id == user_id,
            CollegeMembership.status == MembershipStatus.ACTIVE,
        )
    ).first()
    return (row[0], row[1]) if row else None


def has_suspended_membership(db: Session, user_id: uuid.UUID) -> bool:
    return bool(
        db.execute(
            select(
                exists().where(
                    CollegeMembership.user_id == user_id,
                    CollegeMembership.status == MembershipStatus.SUSPENDED,
                )
            )
        ).scalar()
    )


def holds_privileged_role(db: Session, user_id: uuid.UUID) -> bool:
    """AUTH-013: an ACTIVE FACULTY membership, or a COLLEGE_ADMIN / DEPARTMENT_ADMIN grant on
    an ACTIVE membership. One query, run on every authenticated request."""
    privileged_grant = exists().where(
        RoleGrant.college_id == CollegeMembership.college_id,
        RoleGrant.membership_id == CollegeMembership.id,
        RoleGrant.role.in_((Role.COLLEGE_ADMIN, Role.DEPARTMENT_ADMIN)),
    )
    query = select(
        exists().where(
            CollegeMembership.user_id == user_id,
            CollegeMembership.status == MembershipStatus.ACTIVE,
            (CollegeMembership.kind == MembershipKind.FACULTY) | privileged_grant,
        )
    )
    return bool(db.execute(query).scalar())


def current_membership_view(db: Session, user_id: uuid.UUID) -> MembershipView | None:
    """The user's open membership for /me: the ACTIVE one if any, else the newest PENDING or
    SUSPENDED one."""
    row = db.execute(
        select(CollegeMembership, College)
        .join(College, College.id == CollegeMembership.college_id)
        .where(CollegeMembership.user_id == user_id, CollegeMembership.status.in_(_OPEN))
        .order_by(
            (CollegeMembership.status == MembershipStatus.ACTIVE).desc(),
            CollegeMembership.created_at.desc(),
        )
        .limit(1)
    ).first()
    if row is None:
        return None
    membership, college = row
    grants = grants_of(db, membership)
    department_ids = {g.department_id for g in grants if g.department_id} | (
        {membership.department_id} if membership.department_id else set()
    )
    departments = {
        d.id: d
        for d in db.execute(
            select(Department).where(
                Department.college_id == college.id, Department.id.in_(department_ids)
            )
        ).scalars()
    }
    return MembershipView(
        membership=membership,
        college=college,
        department=departments.get(membership.department_id) if membership.department_id else None,
        grants=grants,
        grant_departments=departments,
    )
