"""Campus access decisions (Rules R-2.1). Pure functions over loaded rows: they never query."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from app.models import (
    College,
    CollegeMembership,
    CollegeStatus,
    MembershipKind,
    MembershipStatus,
    Role,
    RoleGrant,
)
from app.models.user import PlatformRole, User

MEMBERSHIP_REQUIRED = "membership_required"
MEMBERSHIP_INACTIVE = "membership_inactive"
COLLEGE_INACTIVE = "college_inactive"


@dataclass(frozen=True)
class CampusContext:
    """Who is acting and in which college, for one /campus request. Built only from the
    database (the user's ACTIVE membership), never from anything the client sends."""

    user: User
    membership: CollegeMembership
    college: College
    grants: tuple[RoleGrant, ...]

    @property
    def college_id(self) -> uuid.UUID:
        return self.college.id


def campus_access_problem(
    active: tuple[CollegeMembership, College] | None, has_suspended_membership: bool
) -> str | None:
    """Why the user may not use campus routes (403 code), or None. TENANT-001, MEMBER-009,
    ADMIN-001: only an ACTIVE membership in an ACTIVE college grants access."""
    if active is None:
        return MEMBERSHIP_INACTIVE if has_suspended_membership else MEMBERSHIP_REQUIRED
    membership, college = active
    if membership.status != MembershipStatus.ACTIVE:
        return MEMBERSHIP_INACTIVE
    if college.status != CollegeStatus.ACTIVE:
        return COLLEGE_INACTIVE
    return None


def is_college_admin(grants: Iterable[RoleGrant]) -> bool:
    return any(g.role == Role.COLLEGE_ADMIN for g in grants)


def administered_departments(grants: Iterable[RoleGrant]) -> frozenset[uuid.UUID]:
    """Departments a DEPARTMENT_ADMIN's powers apply to (PRD §11: only granted departments)."""
    return frozenset(
        g.department_id for g in grants if g.role == Role.DEPARTMENT_ADMIN and g.department_id
    )


def uses_privileged_session_limits(user: User, holds_privileged_role: bool) -> bool:
    """AUTH-013 and P-10: platform admins, and users currently holding an ACTIVE FACULTY
    membership or a COLLEGE_ADMIN / DEPARTMENT_ADMIN grant, get the shorter session limits."""
    return user.platform_role == PlatformRole.PLATFORM_ADMIN or holds_privileged_role


# Capabilities on /me: what the navigation may offer (Design.md §4). They describe access,
# not features; every route still checks its own policy.
CAMPUS = "campus"
MANAGE_COLLEGE = "manage_college"
REVIEW_MEMBERSHIPS = "review_memberships"
PLATFORM = "platform"


def capabilities(
    user: User,
    membership: CollegeMembership | None,
    college: College | None,
    grants: Iterable[RoleGrant],
) -> list[str]:
    if user.platform_role == PlatformRole.PLATFORM_ADMIN:
        return [PLATFORM]  # never campus access (P-7, ADMIN-008)
    if membership is None or college is None:
        return []
    if campus_access_problem((membership, college), has_suspended_membership=False) is not None:
        return []
    grants = list(grants)
    found = [CAMPUS]
    if is_college_admin(grants):
        found.append(MANAGE_COLLEGE)
    if is_college_admin(grants) or administered_departments(grants):
        found.append(REVIEW_MEMBERSHIPS)
    return found


# --- college administration (ADMIN-003, DEPT-001/002, MEMBER-011, PRD §11 and §17) ---------


def can_manage_college(campus: CampusContext) -> bool:
    """Departments, roster, invites, member changes, roles, audit log: college admins only."""
    return is_college_admin(campus.grants)


def can_view_directory(campus: CampusContext) -> bool:
    """§17.12: the member directory is for admins only (college admins, department admins)."""
    return is_college_admin(campus.grants) or bool(administered_departments(campus.grants))


def directory_includes(campus: CampusContext, member: CollegeMembership) -> bool:
    """PRD §11: department admins see their departments' students plus the college's
    faculty and staff; college admins see everyone."""
    if is_college_admin(campus.grants):
        return True
    if member.kind != MembershipKind.STUDENT:
        return True
    return member.department_id in administered_departments(campus.grants)


def can_see_contact_details(campus: CampusContext, member: CollegeMembership) -> bool:
    """§17.6: email and roll number go to college admins, and to department admins for
    students of their departments."""
    if is_college_admin(campus.grants):
        return True
    return (
        member.kind == MembershipKind.STUDENT
        and member.department_id in administered_departments(campus.grants)
    )


# Changes a college admin may make to a membership (MEMBER-009/011). ENDED is final;
# PENDING and REJECTED are requests, decided through the approval queue (3d).
MEMBERSHIP_TRANSITIONS: dict[str, frozenset[str]] = {
    MembershipStatus.ACTIVE: frozenset({MembershipStatus.SUSPENDED, MembershipStatus.ENDED}),
    MembershipStatus.SUSPENDED: frozenset({MembershipStatus.ACTIVE, MembershipStatus.ENDED}),
}

STUDENT_CANNOT_HOLD_ROLES = "student_cannot_hold_roles"


def can_change_membership_status(current: str, target: str) -> bool:
    return target in MEMBERSHIP_TRANSITIONS.get(current, frozenset())


def membership_change_needs_reason(target: str) -> bool:
    return target in (MembershipStatus.SUSPENDED, MembershipStatus.ENDED)


def grant_problem(member: CollegeMembership) -> str | None:
    """Why `member` can't receive a role (ADMIN-003, DEPT-002), or None."""
    if member.kind == MembershipKind.STUDENT:
        return STUDENT_CANNOT_HOLD_ROLES
    if member.status != MembershipStatus.ACTIVE:
        return MEMBERSHIP_INACTIVE
    return None


def leaves_no_college_admin(other_active_admins: int, member_is_active_admin: bool) -> bool:
    """MEMBER-011, ADMIN-003: a college always keeps at least one ACTIVE college admin."""
    return member_is_active_admin and other_active_admins == 0
