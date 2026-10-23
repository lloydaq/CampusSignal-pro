"""/me describes the signed-in user's college membership, roles and what they may open
(architecture.md §11.1; Design.md §4: navigation is built from these capabilities)."""

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import CollegeStatus, MembershipKind, MembershipStatus, Role
from tests.conftest import APP_ORIGIN
from tests.integration.auth_helpers import PREFIX, login
from tests.integration.tenancy import PASSWORD, add_member, make_user, roster_entry, two_colleges

pytestmark = pytest.mark.integration

EMAIL = "aarav@northfield.example"


@pytest.fixture
def client(app_factory: Callable[..., FastAPI]) -> TestClient:
    return TestClient(app_factory(), raise_server_exceptions=False, headers={"Origin": APP_ORIGIN})


def me(client: TestClient) -> dict[str, object]:
    assert login(client, EMAIL, PASSWORD).status_code == 200
    response = client.get(f"{PREFIX}/me")
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    return body


def test_without_a_membership(session: Session, client: TestClient) -> None:
    make_user(session, EMAIL)
    session.commit()
    body = me(client)
    assert body["membership"] is None
    assert body["roles"] == []
    assert body["capabilities"] == []


def test_a_student(session: Session, client: TestClient) -> None:
    north, _ = two_colleges(session)
    user = make_user(session, EMAIL)
    entry = roster_entry(session, north, "N-17", email=EMAIL)
    membership = add_member(session, user, north)
    membership.roster_entry_id = entry.id
    session.commit()

    body = me(client)
    assert body["membership"] == {
        "id": str(membership.id),
        "kind": "STUDENT",
        "status": "ACTIVE",
        "college": {
            "id": str(north.id),
            "name": "Northfield Institute",
            "slug": "northfield",
            "timezone": "Asia/Kolkata",
            "status": "ACTIVE",
            "is_demo": False,
        },
        "department": {
            "id": str(north.departments["CSE"].id),
            "code": "CSE",
            "name": "CSE department",
        },
    }
    assert body["roles"] == []
    assert body["capabilities"] == ["campus"]
    # Roster details (roll number, roster name) and request internals never appear here.
    for leaked in ("N-17", "roll", "roster", "verification_flag"):
        assert leaked not in str(body)


def test_roles_and_capabilities_of_admins(session: Session, client: TestClient) -> None:
    north, _ = two_colleges(session)
    user = make_user(session, EMAIL)
    add_member(
        session,
        user,
        north,
        MembershipKind.FACULTY,
        roles=((Role.COLLEGE_ADMIN, None), (Role.DEPARTMENT_ADMIN, "MECH")),
    )
    session.commit()

    body = me(client)
    assert body["roles"] == [
        {"role": "COLLEGE_ADMIN", "department": None},
        {
            "role": "DEPARTMENT_ADMIN",
            "department": {
                "id": str(north.departments["MECH"].id),
                "code": "MECH",
                "name": "MECH department",
            },
        },
    ]
    assert body["capabilities"] == ["campus", "manage_college", "review_memberships"]


def test_a_department_admin_reviews_but_does_not_manage(
    session: Session, client: TestClient
) -> None:
    north, _ = two_colleges(session)
    add_member(
        session,
        make_user(session, EMAIL),
        north,
        MembershipKind.STAFF,
        roles=((Role.DEPARTMENT_ADMIN, "CSE"),),
    )
    session.commit()
    assert me(client)["capabilities"] == ["campus", "review_memberships"]


def test_a_suspended_college_shows_the_membership_but_no_capabilities(
    session: Session, client: TestClient
) -> None:
    north, _ = two_colleges(session)
    north.college.status = CollegeStatus.SUSPENDED
    add_member(
        session,
        make_user(session, EMAIL),
        north,
        MembershipKind.FACULTY,
        roles=((Role.COLLEGE_ADMIN, None),),
    )
    session.commit()
    body = me(client)
    assert body["membership"]["college"]["status"] == "SUSPENDED"  # type: ignore[index]
    assert body["capabilities"] == []


@pytest.mark.parametrize("status", [MembershipStatus.PENDING, MembershipStatus.SUSPENDED])
def test_open_but_inactive_memberships_are_shown_without_capabilities(
    session: Session, client: TestClient, status: MembershipStatus
) -> None:
    north, _ = two_colleges(session)
    add_member(session, make_user(session, EMAIL), north, status=status)
    session.commit()
    body = me(client)
    assert body["membership"]["status"] == status  # type: ignore[index]
    assert body["capabilities"] == []


def test_ended_and_rejected_memberships_are_not_shown(session: Session, client: TestClient) -> None:
    north, river = two_colleges(session)
    user = make_user(session, EMAIL)
    add_member(session, user, north, status=MembershipStatus.ENDED)
    add_member(session, user, river, status=MembershipStatus.REJECTED)
    session.commit()
    assert me(client)["membership"] is None


def test_a_platform_admin(session: Session, client: TestClient) -> None:
    make_user(session, EMAIL, platform_admin=True)
    session.commit()
    body = me(client)
    assert body["membership"] is None
    assert body["capabilities"] == ["platform"]
