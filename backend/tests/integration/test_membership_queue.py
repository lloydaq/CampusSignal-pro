"""The approval queue (MEMBER-004…006, US-03): college admins see every pending request; a
department admin sees only requests whose roster entry is in a department they administer, and
never NO_ROSTER_MATCH ones. Decisions are audited; rejection needs a reason."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from tests.integration.auth_helpers import PREFIX, error_of, scalar
from tests.integration.campus_world import CAMPUS, World, build_world
from tests.integration.platform_helpers import Browser
from tests.integration.tenancy import make_user, roster_entry

pytestmark = pytest.mark.integration

QUEUE = f"{CAMPUS}/membership-requests"


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    world = build_world(session, app_factory())
    roster_entry(session, world.north, "N-201", department="CSE", email=None)
    roster_entry(session, world.north, "N-202", department="MECH", email=None)
    session.commit()
    # Three pending requests: CSE roster entry, MECH roster entry, no roster match.
    for who, roll in (("cse_kid", "N-201"), ("mech_kid", "N-202"), ("ghost", "N-404")):
        make_user(session, f"{who}@northfield.example", name=who.replace("_", " ").title())
        session.commit()
        Browser(world.app, f"{who}@northfield.example").post(
            f"{PREFIX}/me/membership-requests", {"college_slug": "northfield", "roll_number": roll}
        )
    return world


def queue(world: World, who: str) -> dict[str, dict[str, Any]]:
    return {
        r["requester"]["display_name"]: r for r in world.browser(who).get(QUEUE).json()["items"]
    }


def test_a_college_admin_sees_every_request_with_its_evidence(world: World) -> None:
    rows = queue(world, "admin")
    assert set(rows) == {"Cse Kid", "Mech Kid", "Ghost"}
    cse = rows["Cse Kid"]
    assert cse["requester"]["email"] == "cse_kid@northfield.example"
    assert (
        cse["flag"],
        cse["roll_number"],
        cse["roster"]["full_name"],
        cse["roster"]["department"]["code"],
    ) == (
        "NO_ROSTER_EMAIL",
        "N-201",
        "Roster Name",
        "CSE",
    )
    ghost = rows["Ghost"]
    assert (ghost["flag"], ghost["roll_number"], ghost["roster"]) == (
        "NO_ROSTER_MATCH",
        "N-404",
        None,
    )


def test_a_department_admin_sees_only_their_departments_requests(world: World) -> None:
    assert set(queue(world, "dept_admin")) == {"Cse Kid"}  # US-03; no MECH, no NO_ROSTER_MATCH


@pytest.mark.parametrize("who", ["faculty", "student"])
def test_others_have_no_queue(world: World, who: str) -> None:
    response = world.browser(who).get(QUEUE)
    assert response.status_code == 403
    assert "Kid" not in response.text


def request_id(world: World, name: str) -> str:
    return str(queue(world, "admin")[name]["id"])


def test_approving_activates_the_membership_and_audits_it(world: World, conn: Connection) -> None:
    rid = request_id(world, "Cse Kid")
    response = world.browser("dept_admin").post(f"{QUEUE}/{rid}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"
    me = Browser(world.app, "cse_kid@northfield.example").get(f"{PREFIX}/me").json()
    assert me["membership"]["department"]["code"] == "CSE"
    assert me["capabilities"] == ["campus"]
    assert (
        scalar(
            conn,
            "SELECT count(*) FROM audit_log "
            "WHERE action = 'membership.approved' AND target_id = :t",
            t=rid,
        )
        == 1
    )

    again = world.browser("admin").post(f"{QUEUE}/{rid}/approve")
    assert again.status_code == 409
    assert error_of(again)["code"] == "already_decided"


def test_rejecting_needs_a_reason_and_is_audited(world: World, conn: Connection) -> None:
    rid = request_id(world, "Mech Kid")
    assert world.browser("admin").post(f"{QUEUE}/{rid}/reject", {}).status_code == 422  # US-03
    response = world.browser("admin").post(
        f"{QUEUE}/{rid}/reject", {"reason": "Not on this year's roll."}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert (
        scalar(conn, "SELECT reason FROM audit_log WHERE action = 'membership.rejected'")
        == "Not on this year's roll."
    )


def test_a_department_admin_cannot_decide_another_departments_request(world: World) -> None:
    for name in ("Mech Kid", "Ghost"):
        rid = request_id(world, name)
        response = world.browser("dept_admin").post(f"{QUEUE}/{rid}/approve")
        assert response.status_code == 404  # can't see it, so it doesn't exist for them
        assert (
            world.browser("dept_admin").post(f"{QUEUE}/{rid}/reject", {"reason": "x"}).status_code
            == 404
        )


def test_no_roster_match_is_approvable_only_once_the_roster_has_the_entry(
    world: World, session: Session
) -> None:
    rid = request_id(world, "Ghost")
    response = world.browser("admin").post(f"{QUEUE}/{rid}/approve")
    assert response.status_code == 409  # MEMBER-006
    assert error_of(response)["code"] == "no_roster_entry"

    roster_entry(session, world.north, "N-404", department="MECH", email=None)
    session.commit()
    assert world.browser("admin").post(f"{QUEUE}/{rid}/approve").status_code == 200
    me = Browser(world.app, "ghost@northfield.example").get(f"{PREFIX}/me").json()
    assert me["membership"]["department"]["code"] == "MECH"


def test_a_claimed_roster_entry_blocks_approval_until_released(
    world: World, session: Session
) -> None:
    make_user(session, "twin@northfield.example", name="Twin")
    session.commit()
    Browser(world.app, "twin@northfield.example").post(
        f"{PREFIX}/me/membership-requests", {"college_slug": "northfield", "roll_number": "N-001"}
    )
    rid = request_id(world, "Twin")
    assert queue(world, "admin")["Twin"]["flag"] == "ROSTER_CLAIMED"
    response = world.browser("admin").post(f"{QUEUE}/{rid}/approve")
    assert response.status_code == 409  # MEMBER-005
    assert error_of(response)["code"] == "roster_claimed"

    world.browser("admin").patch(
        f"{CAMPUS}/members/{world.members['student'].id}",
        {"status": "ENDED", "reason": "Wrong person"},
    )
    assert world.browser("admin").post(f"{QUEUE}/{rid}/approve").status_code == 200


def test_another_colleges_request_is_404(world: World) -> None:
    rid = request_id(world, "Cse Kid")
    river = world.browser("river_admin")
    assert river.post(f"{QUEUE}/{rid}/approve").status_code == 404
    assert river.post(f"{QUEUE}/{rid}/reject", {"reason": "x"}).status_code == 404
    assert "Kid" not in river.get(QUEUE).text
