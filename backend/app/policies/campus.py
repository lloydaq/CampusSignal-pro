"""Campus access decisions (Rules R-2.1). Pure functions over loaded rows: they never query."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from app.models import College, CollegeMembership, CollegeStatus, MembershipStatus, Role, RoleGrant
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
