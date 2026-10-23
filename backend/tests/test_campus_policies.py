"""Campus policies as pure functions (Rules R-2.1): no database, objects built in memory."""

import uuid

import pytest

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
from app.policies.campus import (
    administered_departments,
    campus_access_problem,
    capabilities,
    is_college_admin,
    uses_privileged_session_limits,
)

CSE = uuid.uuid4()
MECH = uuid.uuid4()


def user(platform_admin: bool = False) -> User:
    return User(
        email="a@northfield.example",
        password_hash="x",
        display_name="A",
        platform_role=PlatformRole.PLATFORM_ADMIN if platform_admin else None,
    )


def active(
    status: MembershipStatus = MembershipStatus.ACTIVE,
    college_status: CollegeStatus = CollegeStatus.ACTIVE,
) -> tuple[CollegeMembership, College]:
    return (
        CollegeMembership(kind=MembershipKind.STUDENT, status=status),
        College(
            name="Northfield Institute", slug="northfield", timezone="UTC", status=college_status
        ),
    )


def grant(role: Role, department: uuid.UUID | None = None) -> RoleGrant:
    return RoleGrant(role=role, department_id=department)


@pytest.mark.parametrize(
    ("membership", "suspended", "problem"),
    [
        (None, False, "membership_required"),
        (None, True, "membership_inactive"),
        (active(), False, None),
        (active(MembershipStatus.SUSPENDED), False, "membership_inactive"),
        (active(college_status=CollegeStatus.ONBOARDING), False, "college_inactive"),
        (active(college_status=CollegeStatus.SUSPENDED), False, "college_inactive"),
    ],
)
def test_campus_access_needs_an_active_membership_in_an_active_college(
    membership: tuple[CollegeMembership, College] | None, suspended: bool, problem: str | None
) -> None:
    assert campus_access_problem(membership, suspended) == problem


def test_department_admin_powers_cover_only_granted_departments() -> None:
    grants = [grant(Role.DEPARTMENT_ADMIN, CSE), grant(Role.ISSUE_COORDINATOR)]
    assert administered_departments(grants) == {CSE}
    assert not is_college_admin(grants)
    assert is_college_admin([grant(Role.COLLEGE_ADMIN)])


@pytest.mark.parametrize(
    ("grants", "expected"),
    [
        ((), ["campus"]),
        ((grant(Role.ISSUE_COORDINATOR),), ["campus"]),
        ((grant(Role.DEPARTMENT_ADMIN, MECH),), ["campus", "review_memberships"]),
        ((grant(Role.COLLEGE_ADMIN),), ["campus", "manage_college", "review_memberships"]),
    ],
)
def test_capabilities_follow_roles(grants: tuple[RoleGrant, ...], expected: list[str]) -> None:
    membership, college = active()
    assert capabilities(user(), membership, college, grants) == expected


def test_no_capabilities_without_campus_access() -> None:
    assert capabilities(user(), None, None, ()) == []
    membership, college = active(college_status=CollegeStatus.SUSPENDED)
    assert capabilities(user(), membership, college, [grant(Role.COLLEGE_ADMIN)]) == []
    membership, college = active(MembershipStatus.PENDING)
    assert capabilities(user(), membership, college, ()) == []


def test_a_platform_admin_only_gets_the_platform() -> None:
    membership, college = active()  # can't happen (P-7), but must not open a campus anyway
    assert capabilities(
        user(platform_admin=True), membership, college, [grant(Role.COLLEGE_ADMIN)]
    ) == ["platform"]


def test_privileged_session_limits() -> None:
    assert uses_privileged_session_limits(user(platform_admin=True), holds_privileged_role=False)
    assert uses_privileged_session_limits(user(), holds_privileged_role=True)
    assert not uses_privileged_session_limits(user(), holds_privileged_role=False)
