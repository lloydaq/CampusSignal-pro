"""The campus context (TENANT-001, architecture.md §7/§9): every /campus request acts in the
college of the user's single ACTIVE membership, read from the database on each request.
Anything the client says about which college it means is ignored.

There are no campus features yet (they arrive in 3b to 3d), so these tests mount a probe route
that only reports the context it was given.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import Campus
from app.models import CollegeStatus, MembershipKind, MembershipStatus, Role
from tests.conftest import APP_ORIGIN
from tests.integration.auth_helpers import error_of, login
from tests.integration.tenancy import (
    PASSWORD,
    add_member,
    make_user,
    two_colleges,
)
from tests.integration.tenancy import (
    Campus as CampusRows,
)

pytestmark = pytest.mark.integration

PROBE = "/api/v1/campus/_probe"
EMAIL = "aarav@northfield.example"


@pytest.fixture
def probe_app(app_factory: Callable[..., FastAPI]) -> FastAPI:
    app = app_factory()
    router = APIRouter()

    @router.get(PROBE)
    def probe(campus: Campus) -> dict[str, Any]:
        return {
            "college_id": str(campus.college_id),
            "membership_id": str(campus.membership.id),
            "roles": sorted(g.role for g in campus.grants),
        }

    app.include_router(router)
    return app


@pytest.fixture
def client(probe_app: FastAPI) -> TestClient:
    return TestClient(probe_app, raise_server_exceptions=False, headers={"Origin": APP_ORIGIN})


@pytest.fixture
def colleges(session: Session) -> tuple[CampusRows, CampusRows]:
    return two_colleges(session)


def signed_in(client: TestClient, email: str = EMAIL) -> TestClient:
    assert login(client, email, PASSWORD).status_code == 200
    return client


def test_signed_out_is_401(client: TestClient) -> None:
    assert client.get(PROBE).status_code == 401


def test_an_active_member_acts_in_their_own_college(
    session: Session, client: TestClient, colleges: tuple[CampusRows, CampusRows]
) -> None:
    north, river = colleges
    user = make_user(session, EMAIL)
    membership = add_member(
        session, user, north, MembershipKind.FACULTY, roles=((Role.COLLEGE_ADMIN, None),)
    )
    # Grants on someone else's membership in another college must not leak in.
    add_member(
        session,
        make_user(session, "r@riverside.example"),
        river,
        MembershipKind.FACULTY,
        roles=((Role.ISSUE_COORDINATOR, None),),
    )
    session.commit()

    body = signed_in(client).get(PROBE).json()
    assert body == {
        "college_id": str(north.id),
        "membership_id": str(membership.id),
        "roles": ["COLLEGE_ADMIN"],
    }


def test_client_supplied_college_identifiers_are_ignored(
    session: Session, client: TestClient, colleges: tuple[CampusRows, CampusRows]
) -> None:
    north, river = colleges
    add_member(session, make_user(session, EMAIL), north)
    session.commit()
    signed_in(client)
    for response in (
        client.get(PROBE, params={"college_id": str(river.id), "college": "riverside"}),
        client.get(PROBE, headers={"X-College": str(river.id), "X-College-Id": "riverside"}),
    ):
        assert response.json()["college_id"] == str(north.id)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (None, "membership_required"),
        (MembershipStatus.PENDING, "membership_required"),
        (MembershipStatus.REJECTED, "membership_required"),
        (MembershipStatus.ENDED, "membership_required"),
        (MembershipStatus.SUSPENDED, "membership_inactive"),
    ],
)
def test_without_an_active_membership_campus_access_is_403(
    session: Session,
    client: TestClient,
    colleges: tuple[CampusRows, CampusRows],
    status: MembershipStatus | None,
    code: str,
) -> None:
    north, _ = colleges
    user = make_user(session, EMAIL)
    if status is not None:
        add_member(session, user, north, status=status)
    session.commit()

    response = signed_in(client).get(PROBE)
    assert response.status_code == 403
    assert error_of(response)["code"] == code


@pytest.mark.parametrize("college_status", [CollegeStatus.ONBOARDING, CollegeStatus.SUSPENDED])
def test_members_of_an_inactive_college_get_college_inactive(
    session: Session,
    client: TestClient,
    colleges: tuple[CampusRows, CampusRows],
    college_status: CollegeStatus,
) -> None:
    north, _ = colleges
    north.college.status = college_status
    add_member(session, make_user(session, EMAIL), north)
    session.commit()

    response = signed_in(client).get(PROBE)
    assert response.status_code == 403
    assert error_of(response)["code"] == "college_inactive"  # US-11
    assert str(north.id) not in response.text


def test_changes_apply_on_the_next_request(
    session: Session, client: TestClient, colleges: tuple[CampusRows, CampusRows]
) -> None:
    north, _ = colleges
    membership = add_member(session, make_user(session, EMAIL), north)
    session.commit()
    signed_in(client)
    assert client.get(PROBE).status_code == 200

    membership.status = MembershipStatus.SUSPENDED
    session.commit()
    assert error_of(client.get(PROBE))["code"] == "membership_inactive"

    membership.status = MembershipStatus.ACTIVE
    north.college.status = CollegeStatus.SUSPENDED
    session.commit()
    assert error_of(client.get(PROBE))["code"] == "college_inactive"


def test_a_platform_admin_has_no_campus(
    session: Session, client: TestClient, colleges: tuple[CampusRows, CampusRows]
) -> None:
    make_user(session, EMAIL, platform_admin=True)
    session.commit()
    response = signed_in(client).get(PROBE)
    assert response.status_code == 403
    assert error_of(response)["code"] == "membership_required"


def test_after_moving_colleges_the_new_college_applies(
    session: Session, client: TestClient, colleges: tuple[CampusRows, CampusRows]
) -> None:
    north, river = colleges
    user = make_user(session, EMAIL)
    add_member(session, user, north, status=MembershipStatus.ENDED)
    add_member(session, user, river)
    session.commit()
    assert signed_in(client).get(PROBE).json()["college_id"] == str(river.id)
