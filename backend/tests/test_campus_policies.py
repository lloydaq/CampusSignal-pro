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
    CampusContext,
    administered_departments,
    campus_access_problem,
    can_change_membership_status,
    can_see_contact_details,
    can_view_directory,
    capabilities,
    directory_includes,
    grant_problem,
    is_college_admin,
    leaves_no_college_admin,
    membership_change_needs_reason,
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


# --- college administration ----------------------------------------------------------------


def ctx(*grants: RoleGrant) -> CampusContext:
    membership, college = active()
    return CampusContext(user=user(), membership=membership, college=college, grants=tuple(grants))


def member(kind: MembershipKind, department: uuid.UUID | None = CSE) -> CollegeMembership:
    return CollegeMembership(kind=kind, status=MembershipStatus.ACTIVE, department_id=department)


def test_directory_and_contact_visibility() -> None:
    college_admin = ctx(grant(Role.COLLEGE_ADMIN))
    cse_admin = ctx(grant(Role.DEPARTMENT_ADMIN, CSE))
    plain = ctx()
    cse_student, mech_student = member(MembershipKind.STUDENT), member(MembershipKind.STUDENT, MECH)
    faculty = member(MembershipKind.FACULTY, MECH)

    assert can_view_directory(college_admin) and can_view_directory(cse_admin)
    assert not can_view_directory(plain) and not can_view_directory(
        ctx(grant(Role.ISSUE_COORDINATOR))
    )

    assert directory_includes(cse_admin, cse_student) and directory_includes(cse_admin, faculty)
    assert not directory_includes(cse_admin, mech_student)
    assert directory_includes(college_admin, mech_student)

    assert can_see_contact_details(cse_admin, cse_student)
    assert not can_see_contact_details(cse_admin, faculty)  # PRD §17.6
    assert not can_see_contact_details(cse_admin, mech_student)
    assert can_see_contact_details(college_admin, faculty)


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        ("ACTIVE", "SUSPENDED", True),
        ("ACTIVE", "ENDED", True),
        ("SUSPENDED", "ACTIVE", True),
        ("SUSPENDED", "ENDED", True),
        ("ENDED", "ACTIVE", False),
        ("PENDING", "ACTIVE", False),  # requests go through the approval queue
        ("REJECTED", "ACTIVE", False),
    ],
)
def test_membership_changes(current: str, target: str, allowed: bool) -> None:
    assert can_change_membership_status(current, target) is allowed


def test_reasons_and_grants() -> None:
    assert membership_change_needs_reason("SUSPENDED") and membership_change_needs_reason("ENDED")
    assert not membership_change_needs_reason("ACTIVE")
    assert grant_problem(member(MembershipKind.STUDENT)) == "student_cannot_hold_roles"
    suspended = member(MembershipKind.STAFF)
    suspended.status = MembershipStatus.SUSPENDED
    assert grant_problem(suspended) == "membership_inactive"
    assert grant_problem(member(MembershipKind.STAFF)) is None


def test_a_college_keeps_one_admin() -> None:
    assert leaves_no_college_admin(other_active_admins=0, member_is_active_admin=True)
    assert not leaves_no_college_admin(other_active_admins=1, member_is_active_admin=True)
    assert not leaves_no_college_admin(other_active_admins=0, member_is_active_admin=False)
