"""Joining a college by roll number (MEMBER-002…005, MEMBER-008/010, US-02, P-7).

Only a verified email that matches an unclaimed roster entry activates at once. Every other
outcome gives the requester the same answer, so roll numbers can't be probed (MEMBER-004);
the reason is kept for approvers only.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from tests.integration.auth_helpers import PREFIX, error_of, scalar
from tests.integration.campus_world import World, build_world
from tests.integration.platform_helpers import Browser
from tests.integration.tenancy import make_user, roster_entry

pytestmark = pytest.mark.integration

REQUESTS = f"{PREFIX}/me/membership-requests"
NEWCOMER = "newcomer@northfield.example"


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    world = build_world(session, app_factory())
    roster_entry(session, world.north, "N-100", department="MECH", email=NEWCOMER)  # their own row
    roster_entry(session, world.north, "N-101", email=None)  # no email on the roster
    roster_entry(session, world.north, "N-102", email="someone.else@northfield.example")
    session.commit()
    return world


def newcomer(
    world: World, session: Session, *, verified: bool = True, email: str = NEWCOMER
) -> Browser:
    make_user(session, email, name="New Comer", verified=verified)
    session.commit()
    return Browser(world.app, email)


def ask(browser: Browser, roll: str, slug: str = "northfield") -> Any:
    return browser.post(REQUESTS, {"college_slug": slug, "roll_number": roll})


def flag_of(conn: Connection, email: str = NEWCOMER) -> Any:
    return conn.exec_driver_sql(
        "SELECT m.status, m.verification_flag, m.submitted_roll_number, m.department_id "
        "FROM college_memberships m JOIN users u ON u.id = m.user_id WHERE u.email = %s",
        (email,),
    ).one()


def test_the_college_directory_lists_active_colleges_only(world: World, session: Session) -> None:
    world.river.college.status = "SUSPENDED"
    session.commit()
    body = newcomer(world, session).get(f"{PREFIX}/colleges").json()
    assert body == {"items": [{"name": "Northfield Institute", "slug": "northfield"}]}


def test_a_matching_roster_email_activates_at_once(
    world: World, session: Session, conn: Connection
) -> None:
    browser = newcomer(world, session)
    response = ask(browser, " n-100 ")  # trimmed and case-insensitive
    assert response.status_code == 201
    assert response.json()["status"] == "ACTIVE"
    me = browser.get(f"{PREFIX}/me").json()
    assert me["membership"]["status"] == "ACTIVE"
    assert me["membership"]["department"]["code"] == "MECH"  # from the roster entry
    assert me["capabilities"] == ["campus"]
    assert (
        scalar(conn, "SELECT count(*) FROM audit_log WHERE action = 'membership.auto_activated'")
        == 1
    )


UNIFORM = {"status": "PENDING", "message": "Request sent. Northfield Institute will review it."}


@pytest.mark.parametrize(
    ("roll", "flag"),
    [
        ("N-101", "NO_ROSTER_EMAIL"),
        ("N-102", "EMAIL_MISMATCH"),
        ("N-001", "ROSTER_CLAIMED"),  # the world's student already holds it
        ("N-999", "NO_ROSTER_MATCH"),
    ],
)
def test_every_other_outcome_looks_the_same_to_the_requester(
    world: World, session: Session, conn: Connection, roll: str, flag: str
) -> None:
    browser = newcomer(world, session)
    response = ask(browser, roll)
    assert response.status_code == 202
    assert response.json() == UNIFORM  # US-02: byte-identical apart from ids (there are none)
    me = browser.get(f"{PREFIX}/me").json()
    assert me["membership"]["status"] == "PENDING"
    assert me["membership"]["department"] is None  # a roster department would reveal a match
    assert me["capabilities"] == []
    status, stored_flag, submitted, _ = flag_of(conn)
    assert (status, stored_flag) == ("PENDING", flag)
    assert submitted == ("N-999" if flag == "NO_ROSTER_MATCH" else None)


def test_an_unverified_email_is_refused(world: World, session: Session, conn: Connection) -> None:
    response = ask(newcomer(world, session, verified=False), "N-100")
    assert response.status_code == 403  # US-02
    assert error_of(response)["code"] == "email_unverified"
    assert error_of(response)["message"] == "Verify your email first."
    assert (
        scalar(
            conn,
            "SELECT count(*) FROM college_memberships "
            "WHERE roster_entry_id IS NOT NULL AND status = 'PENDING'",
        )
        == 0
    )


def test_a_platform_admin_cannot_request(world: World, session: Session) -> None:
    make_user(session, "ops@campussignal.example", platform_admin=True)
    session.commit()
    response = ask(Browser(world.app, "ops@campussignal.example"), "N-100")
    assert response.status_code == 403
    assert error_of(response)["code"] == "platform_admin_cannot_join"


def test_an_active_member_cannot_request_another(world: World) -> None:
    response = ask(world.browser("student"), "R-001", slug="riverside")
    assert response.status_code == 409  # US-02
    assert error_of(response)["code"] == "already_member"


def test_one_pending_request_at_a_time(world: World, session: Session) -> None:
    browser = newcomer(world, session)
    assert ask(browser, "N-999").status_code == 202
    response = ask(browser, "R-001", slug="riverside")
    assert response.status_code == 409
    assert error_of(response)["code"] == "request_pending"


def test_unknown_or_inactive_colleges_are_404(world: World, session: Session) -> None:
    browser = newcomer(world, session)
    assert ask(browser, "N-100", slug="nowhere").status_code == 404
    world.north.college.status = "SUSPENDED"
    session.commit()
    assert ask(browser, "N-100").status_code == 404


def test_requests_are_limited_to_five_a_day(world: World, session: Session, clock: Any) -> None:
    browser = newcomer(world, session)
    for _ in range(5):
        response = ask(browser, "x y")  # malformed: still counts, so probing is capped
        assert response.status_code == 422
    limited = ask(browser, "N-100")
    assert limited.status_code == 429  # MEMBER-010
    assert int(limited.headers["Retry-After"]) > 0
    clock.advance(hours=24, minutes=1)
    assert ask(browser, "N-100").status_code == 201


def test_signed_out_is_401(world: World) -> None:
    assert ask(Browser(world.app), "N-100").status_code == 401


def test_the_requester_sees_a_rejection_reason_but_never_the_flag(
    world: World, session: Session
) -> None:
    browser = newcomer(world, session)
    ask(browser, "N-102")
    request_id = (
        world.browser("admin").get("/api/v1/campus/membership-requests").json()["items"][0]["id"]
    )
    world.browser("admin").post(
        f"/api/v1/campus/membership-requests/{request_id}/reject",
        {"reason": "Use your college email."},
    )
    mine = browser.get(REQUESTS).json()["items"]
    assert mine == [
        {
            "id": request_id,
            "college": {"name": "Northfield Institute", "slug": "northfield"},
            "status": "REJECTED",
            "decision_reason": "Use your college email.",
            "created_at": mine[0]["created_at"],
        }
    ]
    assert "EMAIL_MISMATCH" not in str(mine) and "N-102" not in str(mine)
    assert browser.get(f"{PREFIX}/me").json()["membership"] is None
    assert ask(browser, "N-100").status_code == 201  # after a rejection, a new request is fine
