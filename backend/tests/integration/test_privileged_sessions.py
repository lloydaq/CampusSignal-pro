"""Privileged sessions (AUTH-013, US-17): an ACTIVE FACULTY membership or a COLLEGE_ADMIN /
DEPARTMENT_ADMIN grant shortens sessions to 24 h idle / 7 d absolute. The tier is worked out
on every request from current roles, so granting a role can end an older session at once."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import MembershipKind, MembershipStatus, Role
from tests.conftest import APP_ORIGIN
from tests.integration.auth_helpers import PREFIX, login
from tests.integration.tenancy import PASSWORD, add_member, grant, make_user, two_colleges

pytestmark = pytest.mark.integration

EMAIL = "member@northfield.example"
WEEK_SECONDS = 7 * 24 * 3600
MONTH_SECONDS = 30 * 24 * 3600


@pytest.fixture
def client(app_factory: Callable[..., FastAPI]) -> TestClient:
    return TestClient(app_factory(), raise_server_exceptions=False, headers={"Origin": APP_ORIGIN})


def sign_in(client: TestClient) -> int:
    response = login(client, EMAIL, PASSWORD)
    assert response.status_code == 200
    cookie = next(h for h in response.headers.get_list("set-cookie") if h.startswith("cs_session="))
    return int(cookie.lower().split("max-age=")[1].split(";")[0])


def member(
    session: Session,
    kind: MembershipKind,
    roles: tuple[tuple[Role, str | None], ...] = (),
    **kw: Any,
) -> Any:
    north, _ = two_colleges(session)
    membership = add_member(session, make_user(session, EMAIL), north, kind, roles=roles, **kw)
    session.commit()
    return north, membership


def test_a_faculty_session_idles_out_after_24_hours_but_a_student_one_does_not(
    session: Session, client: TestClient, clock: Any
) -> None:
    member(session, MembershipKind.FACULTY)
    assert sign_in(client) == WEEK_SECONDS
    clock.advance(hours=23)
    assert client.get(f"{PREFIX}/me").status_code == 200
    clock.advance(hours=25)
    assert client.get(f"{PREFIX}/me").status_code == 401


def test_a_student_session_survives_a_day_idle(
    session: Session, client: TestClient, clock: Any
) -> None:
    member(session, MembershipKind.STUDENT)
    assert sign_in(client) == MONTH_SECONDS
    clock.advance(hours=25)
    assert client.get(f"{PREFIX}/me").status_code == 200


@pytest.mark.parametrize("role", [Role.COLLEGE_ADMIN, Role.DEPARTMENT_ADMIN])
def test_an_admin_session_ends_after_seven_days_however_active(
    session: Session, client: TestClient, clock: Any, role: Role
) -> None:
    member(
        session,
        MembershipKind.STAFF,
        roles=((role, "CSE" if role == Role.DEPARTMENT_ADMIN else None),),
    )
    sign_in(client)
    for _ in range(7):
        clock.advance(hours=23)  # 161 h after 7 steps
        assert client.get(f"{PREFIX}/me").status_code == 200
    clock.advance(hours=8)  # 169 h: past 7 days since sign-in, only 8 h idle
    assert client.get(f"{PREFIX}/me").status_code == 401


def test_a_student_session_of_the_same_age_is_valid(
    session: Session, client: TestClient, clock: Any
) -> None:
    member(session, MembershipKind.STUDENT)
    sign_in(client)
    for _ in range(8):
        clock.advance(hours=23)
        assert client.get(f"{PREFIX}/me").status_code == 200


def test_granting_department_admin_ends_an_eight_day_old_staff_session(
    session: Session, client: TestClient, clock: Any
) -> None:
    north, membership = member(session, MembershipKind.STAFF)
    sign_in(client)
    for _ in range(8):
        clock.advance(days=1)
        assert client.get(f"{PREFIX}/me").status_code == 200

    grant(session, membership, Role.DEPARTMENT_ADMIN, north.departments["CSE"])
    session.commit()
    assert client.get(f"{PREFIX}/me").status_code == 401


def test_an_issue_coordinator_keeps_standard_limits(
    session: Session, client: TestClient, clock: Any
) -> None:
    member(session, MembershipKind.STAFF, roles=((Role.ISSUE_COORDINATOR, None),))
    assert sign_in(client) == MONTH_SECONDS
    clock.advance(hours=30)
    assert client.get(f"{PREFIX}/me").status_code == 200


def test_roles_on_a_membership_that_is_not_active_do_not_count(
    session: Session, client: TestClient, clock: Any
) -> None:
    member(
        session,
        MembershipKind.FACULTY,
        roles=((Role.COLLEGE_ADMIN, None),),
        status=MembershipStatus.ENDED,
    )
    assert sign_in(client) == MONTH_SECONDS
    clock.advance(hours=30)
    assert client.get(f"{PREFIX}/me").status_code == 200
