"""Migration 0004 on a disposable Postgres: the database itself keeps colleges apart and
enforces the membership rules (architecture.md §8.2, §9; MEMBER-005/008, ADMIN-003).

Each violation happens inside a savepoint so the test transaction stays usable.
"""

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFound
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
from app.repositories.scoped import get_in_college
from tests.integration.tenancy import (
    Campus,
    add_member,
    grant,
    make_user,
    roster_entry,
    two_colleges,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def colleges(session: Session) -> tuple[Campus, Campus]:
    return two_colleges(session)


def rejects(session: Session, action: Callable[[], object], constraint: str) -> None:
    with pytest.raises(IntegrityError) as caught, session.begin_nested():
        action()
        session.flush()
    assert constraint in str(caught.value.orig)


# --- composite foreign keys: nothing points across colleges --------------------------------


def test_a_roster_entry_cannot_use_another_colleges_department(
    session: Session, colleges: tuple[Campus, Campus]
) -> None:
    north, river = colleges
    rejects(
        session,
        lambda: session.add(
            RosterEntry(
                college_id=north.id,
                department_id=river.departments["CSE"].id,
                roll_number="N-1",
                full_name="X",
                program="B.Tech",
                admission_year=2024,
            )
        ),
        "fk_roster_entries_department",
    )


def test_a_membership_cannot_use_another_colleges_department_or_roster_entry(
    session: Session, colleges: tuple[Campus, Campus]
) -> None:
    north, river = colleges
    user = make_user(session, "a@northfield.example")
    rejects(
        session,
        lambda: session.add(
            CollegeMembership(
                user_id=user.id,
                college_id=north.id,
                kind=MembershipKind.STUDENT,
                status=MembershipStatus.ACTIVE,
                department_id=river.departments["CSE"].id,
            )
        ),
        "fk_college_memberships_department",
    )
    river_entry = roster_entry(session, river, "R-1")
    rejects(
        session,
        lambda: session.add(
            CollegeMembership(
                user_id=user.id,
                college_id=north.id,
                kind=MembershipKind.STUDENT,
                status=MembershipStatus.PENDING,
                roster_entry_id=river_entry.id,
            )
        ),
        "fk_college_memberships_roster_entry",
    )


def test_a_grant_cannot_attach_to_another_colleges_membership_or_department(
    session: Session, colleges: tuple[Campus, Campus]
) -> None:
    north, river = colleges
    river_member = add_member(
        session, make_user(session, "r@riverside.example"), river, MembershipKind.FACULTY
    )
    rejects(
        session,
        lambda: session.add(
            RoleGrant(college_id=north.id, membership_id=river_member.id, role=Role.COLLEGE_ADMIN)
        ),
        "fk_role_grants_membership",
    )
    rejects(
        session,
        lambda: session.add(
            RoleGrant(
                college_id=river.id,
                membership_id=river_member.id,
                role=Role.DEPARTMENT_ADMIN,
                department_id=north.departments["CSE"].id,
            )
        ),
        "fk_role_grants_department",
    )


# --- membership rules ----------------------------------------------------------------------


def test_a_user_has_at_most_one_active_membership(
    session: Session, colleges: tuple[Campus, Campus]
) -> None:
    north, river = colleges
    user = make_user(session, "a@northfield.example")
    first = add_member(session, user, north)
    rejects(
        session,
        lambda: add_member(session, user, river),
        "uq_college_memberships_one_active_per_user",
    )

    first.status = MembershipStatus.ENDED  # graduated: a new ACTIVE membership is allowed
    session.flush()
    add_member(session, user, river)


def test_one_open_request_or_membership_per_user_and_college(
    session: Session, colleges: tuple[Campus, Campus]
) -> None:
    north, _ = colleges
    user = make_user(session, "a@northfield.example")
    add_member(session, user, north, status=MembershipStatus.PENDING)
    rejects(
        session,
        lambda: add_member(session, user, north, status=MembershipStatus.PENDING),
        "uq_college_memberships_open_per_college",
    )


def test_rejected_and_ended_memberships_do_not_block_a_new_request(
    session: Session, colleges: tuple[Campus, Campus]
) -> None:
    north, _ = colleges
    user = make_user(session, "a@northfield.example")
    add_member(session, user, north, status=MembershipStatus.REJECTED)
    add_member(session, user, north, status=MembershipStatus.ENDED)
    add_member(session, user, north, status=MembershipStatus.PENDING)


def test_a_roster_entry_backs_at_most_one_active_membership(
    session: Session, colleges: tuple[Campus, Campus]
) -> None:
    north, _ = colleges
    entry = roster_entry(session, north, "N-1")

    def member(email: str, status: MembershipStatus) -> None:
        session.add(
            CollegeMembership(
                user_id=make_user(session, email).id,
                college_id=north.id,
                kind=MembershipKind.STUDENT,
                status=status,
                roster_entry_id=entry.id,
            )
        )

    member("a@northfield.example", MembershipStatus.ACTIVE)
    session.flush()
    member("b@northfield.example", MembershipStatus.PENDING)  # a claim waiting for review is fine
    session.flush()
    rejects(
        session,
        lambda: member("c@northfield.example", MembershipStatus.ACTIVE),
        "uq_college_memberships_one_active_per_roster_entry",
    )


def test_the_raw_roll_number_is_kept_only_without_a_roster_match(
    session: Session, colleges: tuple[Campus, Campus]
) -> None:
    north, _ = colleges
    user = make_user(session, "a@northfield.example")
    rejects(
        session,
        lambda: session.add(
            CollegeMembership(
                user_id=user.id,
                college_id=north.id,
                kind=MembershipKind.STUDENT,
                status=MembershipStatus.PENDING,
                verification_flag="EMAIL_MISMATCH",
                submitted_roll_number="N-404",
            )
        ),
        "ck_college_memberships_roll_number_only_without_match",
    )


# --- role grants ---------------------------------------------------------------------------


def test_department_admin_needs_a_department_and_other_roles_must_not_have_one(
    session: Session, colleges: tuple[Campus, Campus]
) -> None:
    north, _ = colleges
    staff = add_member(
        session, make_user(session, "s@northfield.example"), north, MembershipKind.STAFF
    )
    check = "ck_role_grants_department_only_for_department_admin"
    rejects(session, lambda: grant(session, staff, Role.DEPARTMENT_ADMIN), check)
    rejects(
        session, lambda: grant(session, staff, Role.COLLEGE_ADMIN, north.departments["CSE"]), check
    )
    grant(session, staff, Role.DEPARTMENT_ADMIN, north.departments["CSE"])
    grant(session, staff, Role.DEPARTMENT_ADMIN, north.departments["MECH"])  # several departments


def test_the_same_grant_cannot_be_given_twice(
    session: Session, colleges: tuple[Campus, Campus]
) -> None:
    north, _ = colleges
    staff = add_member(
        session, make_user(session, "s@northfield.example"), north, MembershipKind.STAFF
    )
    grant(session, staff, Role.COLLEGE_ADMIN)
    # NULLS NOT DISTINCT: two department-less COLLEGE_ADMIN grants are duplicates.
    rejects(
        session,
        lambda: grant(session, staff, Role.COLLEGE_ADMIN),
        "uq_role_grants_membership_id_role_department_id",
    )


# --- colleges and departments --------------------------------------------------------------


def test_slugs_are_unique_and_well_formed(
    session: Session, colleges: tuple[Campus, Campus]
) -> None:
    rejects(
        session,
        lambda: session.add(College(name="X", slug="northfield", timezone="UTC")),
        "uq_colleges_slug",
    )

    def college_with_slug(slug: str) -> Callable[[], object]:
        return lambda: session.add(College(name="X", slug=slug, timezone="UTC"))

    for slug in ("Northfield", "-north", "north_field", "a" * 51):
        rejects(session, college_with_slug(slug), "ck_colleges_slug_format")


def test_department_codes_are_unique_per_college_only(
    session: Session, colleges: tuple[Campus, Campus]
) -> None:
    north, river = colleges
    assert north.departments["CSE"].code == river.departments["CSE"].code
    rejects(
        session,
        lambda: session.add(Department(college_id=north.id, code="CSE", name="Again")),
        "uq_departments_college_id_code",
    )


def test_audit_entries_reference_real_colleges(session: Session) -> None:
    rejects(
        session,
        lambda: session.execute(
            text(
                "INSERT INTO audit_log (action, college_id) "
                "VALUES ('test.x', '00000000-0000-0000-0000-000000000001')"
            )
        ),
        "fk_audit_log_college_id_colleges",
    )


# --- the scoped lookup helper (repositories) -----------------------------------------------


def test_get_in_college_finds_only_this_colleges_rows(
    session: Session, colleges: tuple[Campus, Campus]
) -> None:
    north, river = colleges
    river_cse = river.departments["CSE"]
    assert get_in_college(session, Department, river.id, river_cse.id) is river_cse
    with pytest.raises(NotFound):
        get_in_college(session, Department, north.id, river_cse.id)  # exists, but not here
    with pytest.raises(NotFound):
        get_in_college(session, Department, north.id, uuid.uuid4())  # doesn't exist: same error
