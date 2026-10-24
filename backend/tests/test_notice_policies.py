"""Notice policies as pure functions (NOTICE-002, 004, 006): no database, objects in memory."""

import uuid

import pytest

from app.models import (
    College,
    CollegeMembership,
    MembershipKind,
    MembershipStatus,
    Notice,
    NoticeScope,
    NoticeStatus,
    Role,
    RoleGrant,
)
from app.models.user import User
from app.policies.campus import CampusContext
from app.policies.notices import (
    can_edit_department_description,
    can_manage_notice,
    can_publish_in,
    can_publish_notices,
    can_read_notice,
    managed_audience,
    published_audience,
)

CSE = uuid.uuid4()
MECH = uuid.uuid4()
CIVIL = uuid.uuid4()


def ctx(
    *grants: RoleGrant,
    department: uuid.UUID | None = None,
    kind: MembershipKind = MembershipKind.STUDENT,
) -> CampusContext:
    return CampusContext(
        user=User(email="a@northfield.example", password_hash="x", display_name="A"),
        membership=CollegeMembership(
            kind=kind, status=MembershipStatus.ACTIVE, department_id=department
        ),
        college=College(name="Northfield Institute", slug="northfield", timezone="UTC"),
        grants=tuple(grants),
    )


def grant(role: Role, department: uuid.UUID | None = None) -> RoleGrant:
    return RoleGrant(role=role, department_id=department)


def notice(
    scope: NoticeScope = NoticeScope.COLLEGE,
    department: uuid.UUID | None = None,
    status: NoticeStatus = NoticeStatus.PUBLISHED,
) -> Notice:
    return Notice(scope=scope, department_id=department, status=status)


COLLEGE_ADMIN = ctx(grant(Role.COLLEGE_ADMIN), kind=MembershipKind.STAFF)
CSE_ADMIN = ctx(grant(Role.DEPARTMENT_ADMIN, CSE), department=CSE, kind=MembershipKind.FACULTY)
CSE_AND_MECH_ADMIN = ctx(grant(Role.DEPARTMENT_ADMIN, CSE), grant(Role.DEPARTMENT_ADMIN, MECH))
CSE_STUDENT = ctx(department=CSE)
MECH_STUDENT = ctx(department=MECH)
NO_DEPARTMENT_STAFF = ctx(kind=MembershipKind.STAFF)
COORDINATOR = ctx(grant(Role.ISSUE_COORDINATOR), department=CSE, kind=MembershipKind.STAFF)


@pytest.mark.parametrize(
    ("campus", "scope", "department", "allowed"),
    [
        # NOTICE-002: college admins publish anywhere; department admins only in their department.
        (COLLEGE_ADMIN, NoticeScope.COLLEGE, None, True),
        (COLLEGE_ADMIN, NoticeScope.DEPARTMENT, CSE, True),
        (CSE_ADMIN, NoticeScope.DEPARTMENT, CSE, True),
        (CSE_ADMIN, NoticeScope.DEPARTMENT, MECH, False),
        (CSE_ADMIN, NoticeScope.COLLEGE, None, False),
        (CSE_AND_MECH_ADMIN, NoticeScope.DEPARTMENT, MECH, True),
        (CSE_AND_MECH_ADMIN, NoticeScope.DEPARTMENT, CIVIL, False),
        # Everyone else can't publish at all, whatever their department.
        (CSE_STUDENT, NoticeScope.DEPARTMENT, CSE, False),
        (CSE_STUDENT, NoticeScope.COLLEGE, None, False),
        (COORDINATOR, NoticeScope.DEPARTMENT, CSE, False),
        (NO_DEPARTMENT_STAFF, NoticeScope.COLLEGE, None, False),
    ],
)
def test_who_may_publish_where(
    campus: CampusContext, scope: NoticeScope, department: uuid.UUID | None, allowed: bool
) -> None:
    assert can_publish_in(campus, scope, department) is allowed


def test_who_may_publish_anything_at_all() -> None:
    assert can_publish_notices(COLLEGE_ADMIN) and can_publish_notices(CSE_ADMIN)
    assert not any(can_publish_notices(c) for c in (CSE_STUDENT, COORDINATOR, NO_DEPARTMENT_STAFF))


@pytest.mark.parametrize(
    ("campus", "target", "allowed"),
    [
        (COLLEGE_ADMIN, notice(), True),
        (COLLEGE_ADMIN, notice(NoticeScope.DEPARTMENT, MECH), True),
        (CSE_ADMIN, notice(NoticeScope.DEPARTMENT, CSE), True),
        (CSE_ADMIN, notice(NoticeScope.DEPARTMENT, MECH), False),
        (CSE_ADMIN, notice(), False),  # a department admin can't touch a college notice
        (CSE_STUDENT, notice(NoticeScope.DEPARTMENT, CSE), False),
    ],
)
def test_who_may_manage_a_notice(campus: CampusContext, target: Notice, allowed: bool) -> None:
    # NOTICE-006: the same people who can publish in that scope; an author who lost the
    # role is simply no longer one of them.
    assert can_manage_notice(campus, target) is allowed


@pytest.mark.parametrize("status", [NoticeStatus.DRAFT, NoticeStatus.WITHDRAWN])
def test_only_managers_see_drafts_and_withdrawn_notices(status: NoticeStatus) -> None:
    college = notice(status=status)
    cse = notice(NoticeScope.DEPARTMENT, CSE, status)
    assert can_read_notice(COLLEGE_ADMIN, college) and can_read_notice(COLLEGE_ADMIN, cse)
    assert can_read_notice(CSE_ADMIN, cse)
    assert not can_read_notice(CSE_ADMIN, college)  # not theirs to manage
    for reader in (CSE_STUDENT, MECH_STUDENT, NO_DEPARTMENT_STAFF, COORDINATOR):
        assert not can_read_notice(reader, college)
        assert not can_read_notice(reader, cse)


@pytest.mark.parametrize(
    ("campus", "target", "allowed"),
    [
        # NOTICE-004: a college notice reaches every ACTIVE member.
        (CSE_STUDENT, notice(), True),
        (NO_DEPARTMENT_STAFF, notice(), True),
        (CSE_ADMIN, notice(), True),
        # A department notice reaches that department's members, college admins and its admins.
        (CSE_STUDENT, notice(NoticeScope.DEPARTMENT, CSE), True),
        (MECH_STUDENT, notice(NoticeScope.DEPARTMENT, CSE), False),
        (NO_DEPARTMENT_STAFF, notice(NoticeScope.DEPARTMENT, CSE), False),
        (COLLEGE_ADMIN, notice(NoticeScope.DEPARTMENT, CSE), True),
        (CSE_ADMIN, notice(NoticeScope.DEPARTMENT, CSE), True),
        (CSE_ADMIN, notice(NoticeScope.DEPARTMENT, MECH), False),
        (CSE_AND_MECH_ADMIN, notice(NoticeScope.DEPARTMENT, MECH), True),
        # A department admin who administers MECH but belongs to CSE reads both.
        (
            ctx(grant(Role.DEPARTMENT_ADMIN, MECH), department=CSE),
            notice(NoticeScope.DEPARTMENT, CSE),
            True,
        ),
    ],
)
def test_who_reads_a_published_notice(campus: CampusContext, target: Notice, allowed: bool) -> None:
    assert can_read_notice(campus, target) is allowed


def test_the_audience_helpers_agree_with_the_single_notice_policy() -> None:
    """Lists filter in SQL with these audiences; they must say what can_read_notice says."""
    people = [
        COLLEGE_ADMIN,
        CSE_ADMIN,
        CSE_AND_MECH_ADMIN,
        CSE_STUDENT,
        MECH_STUDENT,
        NO_DEPARTMENT_STAFF,
        COORDINATOR,
    ]
    notices = [
        notice(scope, department, status)
        for status in NoticeStatus
        for scope, department in (
            (NoticeScope.COLLEGE, None),
            (NoticeScope.DEPARTMENT, CSE),
            (NoticeScope.DEPARTMENT, MECH),
            (NoticeScope.DEPARTMENT, CIVIL),
        )
    ]
    for campus in people:
        published = published_audience(campus)
        managed = managed_audience(campus)
        for target in notices:
            by_audience = (
                _in_audience(target, include_college=True, audience=published)
                if target.status == NoticeStatus.PUBLISHED
                else _in_audience(
                    target,
                    include_college=managed.include_college,
                    audience=managed.departments,
                )
            )
            assert by_audience == can_read_notice(campus, target), (campus.grants, target)


def _in_audience(target: Notice, *, include_college: bool, audience: object) -> bool:
    from app.policies.notices import DepartmentAudience

    assert isinstance(audience, DepartmentAudience)
    if target.scope == NoticeScope.COLLEGE:
        return include_college
    assert target.department_id is not None
    return audience.includes(target.department_id)


def test_department_admins_edit_only_the_description_of_their_own_department() -> None:
    assert can_edit_department_description(CSE_ADMIN, CSE)
    assert can_edit_department_description(COLLEGE_ADMIN, MECH)
    assert not can_edit_department_description(CSE_ADMIN, MECH)
    assert not can_edit_department_description(CSE_STUDENT, CSE)
