"""Tenant isolation suite (TENANT-005): every campus route, called by Northfield's college
admin against Riverside, must deny without leaking. Cases live in tests/tenant_isolation_cases.py.
"""

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CollegeMembership, MembershipKind, MembershipStatus, RoleGrant
from tests.integration.auth_helpers import error_of
from tests.integration.campus_world import World, build_world
from tests.integration.tenancy import make_user
from tests.tenant_isolation_cases import CASES, Kind

pytestmark = pytest.mark.integration

# Anything that would only be in a response if Riverside data leaked.
RIVERSIDE_MARKERS = (
    "riverside",
    "River Admin",
    "River Student",
    "River Applicant",
    "R-001",
    "R-404",
)


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    world = build_world(session, app_factory())
    world.river_admin_grant = session.execute(  # type: ignore[attr-defined]
        select(RoleGrant).where(RoleGrant.membership_id == world.members["river_admin"].id)
    ).scalar_one()
    # A pending request at Riverside, from a Riverside applicant.
    applicant = make_user(session, "river_applicant@riverside.example", name="River Applicant")
    world.river_request = CollegeMembership(  # type: ignore[attr-defined]
        user_id=applicant.id,
        college_id=world.river.id,
        kind=MembershipKind.STUDENT,
        status=MembershipStatus.PENDING,
        verification_flag="NO_ROSTER_MATCH",
        submitted_roll_number="R-404",
    )
    session.add(world.river_request)  # type: ignore[attr-defined]
    session.commit()
    # Riverside activity, so its audit log and invites aren't empty.
    river = world.browser("river_admin")
    assert (
        river.post(
            "/api/v1/campus/invites", {"email": "new@riverside.example", "kind": "STAFF"}
        ).status_code
        == 201
    )
    # Riverside notices: one published (with a Riverside-only title), one draft.
    for title, publish in (("Riverside hostel curfew", True), ("Riverside draft plan", False)):
        created = river.post(
            "/api/v1/campus/notices",
            {
                "title": title,
                "body": "Only for Riverside.",
                "category": "GENERAL",
                "scope": "COLLEGE",
                "publish": publish,
            },
        )
        assert created.status_code == 201, created.text
        if publish:
            world.river_notice = created.json()  # type: ignore[attr-defined]
        else:
            world.river_draft = created.json()  # type: ignore[attr-defined]
    return world


def assert_no_riverside_data(text: str) -> None:
    lowered = text.lower()
    for marker in RIVERSIDE_MARKERS:
        assert marker.lower() not in lowered, marker


OPERATIONS = sorted(CASES)


@pytest.mark.parametrize("operation", OPERATIONS, ids=[" ".join(op) for op in OPERATIONS])
def test_northfield_admin_cannot_reach_riverside(world: World, operation: tuple[str, str]) -> None:
    method, _ = operation
    case = CASES[operation]
    path, body = case.request(world)
    response = world.browser("admin").send(method, path, body)

    if case.kind == Kind.OBJECT:
        assert response.status_code == 404, response.text
        assert error_of(response) == {
            "code": "not_found",
            "message": "Not found.",
            "details": None,
            "request_id": error_of(response)["request_id"],
        }
    elif case.kind == Kind.LIST:
        assert response.status_code == 200, response.text
    else:
        assert response.status_code == 422, response.text
        assert any(d["field"] == "college_id" for d in error_of(response)["details"])
    assert_no_riverside_data(response.text)
