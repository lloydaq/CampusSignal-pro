"""Academic setup policies as pure functions (ACADEMIC-001…004, 010; PRD §11): no database."""

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
from app.models.user import User
from app.policies.academic import (
    NOT_ACTIVE_FACULTY,
    NOT_ACTIVE_STUDENT,
    can_manage_catalog,
    can_manage_terms,
    can_read_section,
    enrollment_problem,
    has_own_academics,
    instructor_problem,
    is_teacher,
    managed_departments,
    manages_any_catalog,
    may_read_sections,
)
from app.policies.campus import CampusContext

CSE = uuid.uuid4()
MECH = uuid.uuid4()
ME = uuid.uuid4()
OTHER = uuid.uuid4()


def ctx(
    *roles: tuple[Role, uuid.UUID | None], kind: MembershipKind = MembershipKind.STAFF
) -> CampusContext:
    return CampusContext(
        user=User(email="a@northfield.example", password_hash="x", display_name="A"),
        membership=CollegeMembership(
            id=ME, kind=kind, status=MembershipStatus.ACTIVE, department_id=CSE
        ),
        college=College(
            name="Northfield Institute",
            slug="northfield",
            timezone="UTC",
            status=CollegeStatus.ACTIVE,
        ),
        grants=tuple(RoleGrant(role=r, department_id=d) for r, d in roles),
    )


COLLEGE_ADMIN = ctx((Role.COLLEGE_ADMIN, None), kind=MembershipKind.FACULTY)
CSE_ADMIN = ctx((Role.DEPARTMENT_ADMIN, CSE))
FACULTY = ctx(kind=MembershipKind.FACULTY)
STUDENT = ctx(kind=MembershipKind.STUDENT)
STAFF = ctx()
COORDINATOR = ctx((Role.ISSUE_COORDINATOR, None))


def test_only_college_admins_manage_terms() -> None:
    assert can_manage_terms(COLLEGE_ADMIN)
    for other in (CSE_ADMIN, FACULTY, STUDENT, STAFF, COORDINATOR):
        assert not can_manage_terms(other)


def test_catalog_managers_are_college_admins_and_department_admins_of_that_department() -> None:
    assert can_manage_catalog(COLLEGE_ADMIN, CSE) and can_manage_catalog(COLLEGE_ADMIN, MECH)
    assert can_manage_catalog(CSE_ADMIN, CSE)
    assert not can_manage_catalog(CSE_ADMIN, MECH)
    for other in (FACULTY, STUDENT, STAFF, COORDINATOR):
        assert not can_manage_catalog(other, CSE)
        assert not manages_any_catalog(other)
    assert manages_any_catalog(COLLEGE_ADMIN) and manages_any_catalog(CSE_ADMIN)


def test_managed_departments() -> None:
    assert managed_departments(COLLEGE_ADMIN) is None
    assert managed_departments(CSE_ADMIN) == frozenset({CSE})
    assert managed_departments(FACULTY) == frozenset()


def test_sections_are_read_by_their_managers_and_assigned_faculty() -> None:
    assert can_read_section(COLLEGE_ADMIN, MECH, [])
    assert can_read_section(CSE_ADMIN, CSE, [])
    assert not can_read_section(CSE_ADMIN, MECH, [])
    assert can_read_section(FACULTY, MECH, [ME])
    assert not can_read_section(FACULTY, MECH, [OTHER])
    # Only faculty teach: a student or staff id in the instructor list grants nothing.
    assert not can_read_section(STUDENT, CSE, [ME])
    assert not can_read_section(STAFF, CSE, [ME])


def test_who_may_ask_about_sections_at_all() -> None:
    assert may_read_sections(COLLEGE_ADMIN)
    assert may_read_sections(CSE_ADMIN)
    assert may_read_sections(FACULTY)
    for other in (STUDENT, STAFF, COORDINATOR):
        assert not may_read_sections(other)


def test_own_academics_are_for_students_and_teaching_for_faculty() -> None:
    assert has_own_academics(STUDENT)
    assert not any(has_own_academics(c) for c in (COLLEGE_ADMIN, CSE_ADMIN, FACULTY, STAFF))
    assert is_teacher(FACULTY) and is_teacher(COLLEGE_ADMIN)
    assert not any(is_teacher(c) for c in (CSE_ADMIN, STUDENT, STAFF))


@pytest.mark.parametrize(
    ("kind", "status", "instructor", "student"),
    [
        (MembershipKind.FACULTY, MembershipStatus.ACTIVE, None, NOT_ACTIVE_STUDENT),
        (MembershipKind.STUDENT, MembershipStatus.ACTIVE, NOT_ACTIVE_FACULTY, None),
        (MembershipKind.STAFF, MembershipStatus.ACTIVE, NOT_ACTIVE_FACULTY, NOT_ACTIVE_STUDENT),
        (
            MembershipKind.FACULTY,
            MembershipStatus.SUSPENDED,
            NOT_ACTIVE_FACULTY,
            NOT_ACTIVE_STUDENT,
        ),
        (MembershipKind.STUDENT, MembershipStatus.ENDED, NOT_ACTIVE_FACULTY, NOT_ACTIVE_STUDENT),
        (MembershipKind.STUDENT, MembershipStatus.PENDING, NOT_ACTIVE_FACULTY, NOT_ACTIVE_STUDENT),
    ],
)
def test_who_can_teach_or_be_enrolled(
    kind: MembershipKind, status: MembershipStatus, instructor: str | None, student: str | None
) -> None:
    member = CollegeMembership(kind=kind, status=status)
    assert instructor_problem(member) == instructor
    assert enrollment_problem(member) == student
