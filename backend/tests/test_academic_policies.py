"""Academic setup policies as pure functions (ACADEMIC-001…004, 010; PRD §11): no database."""

import uuid
from datetime import UTC, datetime, timedelta

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
    AttendanceEdit,
    attendance_edit,
    attendance_percentage,
    can_manage_catalog,
    can_manage_terms,
    can_read_section,
    can_record_attendance,
    edit_window_open,
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


# --- attendance (ACADEMIC-005…007) ---------------------------------------------------------

RECORDED = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def test_the_edit_window_closes_exactly_after_its_hours() -> None:
    assert edit_window_open(RECORDED, 48, RECORDED)
    assert edit_window_open(RECORDED, 48, RECORDED + timedelta(hours=48) - timedelta(seconds=1))
    assert not edit_window_open(RECORDED, 48, RECORDED + timedelta(hours=48))
    assert edit_window_open(RECORDED, 72, RECORDED + timedelta(hours=60))


def test_only_assigned_faculty_record_attendance() -> None:
    assert can_record_attendance(FACULTY, [ME])
    assert not can_record_attendance(FACULTY, [OTHER])
    for other in (CSE_ADMIN, STUDENT, STAFF):
        assert not can_record_attendance(other, [ME])
    assert not can_record_attendance(COLLEGE_ADMIN, [OTHER])


def edit_as(
    campus: CampusContext, *, assigned: bool, hours_later: float, department: uuid.UUID = CSE
) -> AttendanceEdit | None:
    return attendance_edit(
        campus,
        department,
        [ME] if assigned else [OTHER],
        created_at=RECORDED,
        window_hours=48,
        now=RECORDED + timedelta(hours=hours_later),
    )


def test_who_edits_attendance_and_how() -> None:
    # The assigned teacher: freely inside the window, then never.
    assert edit_as(FACULTY, assigned=True, hours_later=47) == AttendanceEdit.FACULTY
    assert edit_as(FACULTY, assigned=True, hours_later=48) == AttendanceEdit.WINDOW_CLOSED
    assert edit_as(FACULTY, assigned=False, hours_later=1) is None
    # The section's department admin corrects at any time (with a reason, checked by the service).
    assert edit_as(CSE_ADMIN, assigned=False, hours_later=1) == AttendanceEdit.CORRECTION
    assert edit_as(CSE_ADMIN, assigned=False, hours_later=500) == AttendanceEdit.CORRECTION
    assert edit_as(CSE_ADMIN, assigned=False, hours_later=1, department=MECH) is None
    # A teacher who is also the department's admin corrects after the window closes.
    both = ctx((Role.DEPARTMENT_ADMIN, CSE), kind=MembershipKind.FACULTY)
    assert edit_as(both, assigned=True, hours_later=1) == AttendanceEdit.FACULTY
    assert edit_as(both, assigned=True, hours_later=100) == AttendanceEdit.CORRECTION
    # College admins read attendance but don't change it (PRD §11); nor do students or staff.
    for other in (COLLEGE_ADMIN, STUDENT, STAFF, COORDINATOR):
        assert edit_as(other, assigned=False, hours_later=1) is None


@pytest.mark.parametrize(
    ("held", "attended", "excused", "expected"),
    [
        (0, 0, 0, None),
        (4, 3, 0, 75.0),
        (4, 3, 1, 100.0),  # EXCUSED leaves the denominator
        (3, 1, 0, 33.3),
        (2, 0, 2, None),  # only excused sessions: nothing counts yet
        (10, 0, 0, 0.0),
    ],
)
def test_attendance_percentage(
    held: int, attended: int, excused: int, expected: float | None
) -> None:
    assert attendance_percentage(held, attended, excused) == expected
