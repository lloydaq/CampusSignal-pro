"""Reports and moderation (COMMUNITY-006, 007; US-10 second half): reporting what one can read,
one open report per member per target, the queue by moderator, hiding with a reason the author
is told, dismissing, and the audit trail."""

from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from tests.integration.auth_helpers import error_of
from tests.integration.campus_world import CAMPUS, World, build_world
from tests.integration.conftest import Clock
from tests.integration.platform_helpers import Browser

pytestmark = pytest.mark.integration

POSTS = f"{CAMPUS}/posts"
REPORTS = f"{CAMPUS}/reports"
QUEUE = f"{CAMPUS}/moderation/reports"
WORDS = "Rumour about the hostel warden"  # what the reported post says
REASON = "Unverified claims about a named person"


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    return build_world(session, app_factory())


def post(who: Browser, body: str = WORDS, visibility: str = "COLLEGE") -> dict[str, Any]:
    response = who.post(POSTS, {"body": body, "visibility": visibility})
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def report(who: Browser, **target: Any) -> httpx2.Response:
    return who.post(REPORTS, {"reason": "MISINFORMATION", **target})


def reported(who: Browser, **target: Any) -> dict[str, Any]:
    response = report(who, **target)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def queue(who: Browser, query: str = "") -> list[dict[str, Any]]:
    response = who.get(f"{QUEUE}?{query}")
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def resolve(
    who: Browser, report_id: str, action: str, reason: str | None = REASON
) -> httpx2.Response:
    body: dict[str, Any] = {"action": action}
    if reason is not None:
        body["reason"] = reason
    return who.post(f"{QUEUE}/{report_id}/resolve", body)


def notifications(who: Browser) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = who.get("/api/v1/me/notifications").json()["items"]
    return items


def audit(conn: Connection, target_id: str) -> list[tuple[str, str | None]]:
    return [
        (a, r)
        for a, r in conn.exec_driver_sql(
            "SELECT action, reason FROM audit_log WHERE target_id = %s ORDER BY created_at",
            (target_id,),
        ).all()
    ]


# --- reporting (COMMUNITY-006) ---


def test_a_member_reports_a_post_once(world: World) -> None:
    created = post(world.browser("student"))
    first = reported(world.browser("mech_student"), post_id=created["id"], note="Not true")
    assert first["status"] == "OPEN"
    again = report(world.browser("mech_student"), post_id=created["id"])
    assert again.status_code == 409 and error_of(again)["code"] == "already_reported"
    reported(world.browser("faculty"), post_id=created["id"])  # someone else may


def test_what_can_be_reported(world: World) -> None:
    mine = post(world.browser("student"))
    assert report(world.browser("student"), post_id=mine["id"]).status_code == 403  # own post
    department = post(world.browser("student"), "CSE only", "DEPARTMENT")
    for who in ("mech_student", "river_admin"):
        response = report(world.browser(who), post_id=department["id"])
        assert response.status_code == 404, who
        assert "CSE only" not in response.text
    for body in (
        {"reason": "SPAM"},  # no target
        {"reason": "SPAM", "post_id": mine["id"], "comment_id": mine["id"]},  # two
        {"reason": "BORING", "post_id": mine["id"]},
        {"reason": "SPAM", "post_id": mine["id"], "note": "x" * 501},
        {"reason": "SPAM", "post_id": mine["id"], "college_id": str(world.river.id)},
    ):
        assert world.browser("faculty").post(REPORTS, body).status_code == 422, body


# --- the queue (COMMUNITY-007) ---


def test_the_queue_is_for_moderators_and_scoped_to_their_posts(world: World, clock: Clock) -> None:
    college = post(world.browser("student"), "College post")
    clock.advance(minutes=1)
    department = post(world.browser("student"), "CSE post", "DEPARTMENT")
    for p in (college, department):
        reported(world.browser("faculty"), post_id=p["id"])
        clock.advance(minutes=1)
    reported(world.browser("dept_admin"), post_id=college["id"])

    for who in ("student", "faculty", "mech_student"):
        response = world.browser(who).get(QUEUE)
        assert response.status_code == 403, who
        assert "College post" not in response.text
    everything = queue(world.browser("admin"))
    assert [i["content"]["body"] for i in everything] == [
        "College post",
        "CSE post",
        "College post",
    ]
    assert [i["open_reports"] for i in everything] == [2, 1, 2]
    # A department admin sees their department's posts only (never a college post).
    assert [i["content"]["body"] for i in queue(world.browser("dept_admin"))] == ["CSE post"]
    # Reporters stay private; the reported content's author is named.
    assert "Faculty" not in world.browser("admin").get(QUEUE).text
    assert everything[0]["content"]["author"] == {"name": "Student", "kind": "STUDENT"}
    assert queue(world.browser("river_admin")) == []


# --- hiding (COMMUNITY-007, US-10) ---


def test_hiding_a_post(world: World, conn: Connection, clock: Clock) -> None:  # US-10
    created = post(world.browser("student"))
    first = reported(world.browser("mech_student"), post_id=created["id"])
    reported(world.browser("faculty"), post_id=created["id"])
    clock.advance(minutes=5)
    response = resolve(world.browser("admin"), first["id"], "HIDE")
    assert response.status_code == 200, response.text
    assert response.json() == {"action": "HIDE", "closed_reports": 2}

    # Gone for everyone but moderators; the author sees why.
    for who in ("mech_student", "faculty", "dept_admin"):
        assert WORDS not in [p["body"] for p in world.browser(who).get(POSTS).json()["items"]], who
        assert world.browser(who).get(f"{POSTS}/{created['id']}").status_code == 404, who
    assert WORDS in [p["body"] for p in world.browser("admin").get(POSTS).json()["items"]]
    mine = world.browser("student").get(f"{POSTS}/{created['id']}").json()
    assert mine["status"] == "HIDDEN" and mine["hidden_reason"] == REASON
    # Told, with a link to the post; the title names neither the words nor the reason.
    [told] = notifications(world.browser("student"))
    assert told["type"] == "CONTENT_HIDDEN" and told["subject_id"] == created["id"]
    assert told["title"] == "A moderator hid your post"
    assert audit(conn, created["id"]) == [("community.content_hidden", REASON)]
    assert queue(world.browser("admin")) == []
    assert len(queue(world.browser("admin"), "status=ACTIONED")) == 2
    again = resolve(world.browser("admin"), first["id"], "HIDE")
    assert again.status_code == 409 and error_of(again)["code"] == "already_resolved"


def test_a_department_admin_cannot_hide_a_college_post(world: World) -> None:  # US-10
    college = post(world.browser("student"))
    department = post(world.browser("student"), "CSE post", "DEPARTMENT")
    on_college = reported(world.browser("faculty"), post_id=college["id"])
    on_department = reported(world.browser("faculty"), post_id=department["id"])
    refused = resolve(world.browser("dept_admin"), on_college["id"], "HIDE")
    assert refused.status_code == 403
    assert world.browser("student").get(f"{POSTS}/{college['id']}").json()["status"] == "VISIBLE"
    assert resolve(world.browser("dept_admin"), on_department["id"], "HIDE").status_code == 200
    # Members and other colleges can't resolve at all.
    assert resolve(world.browser("faculty"), on_college["id"], "HIDE").status_code == 403
    response = resolve(world.browser("river_admin"), on_college["id"], "HIDE")
    assert response.status_code == 404 and WORDS not in response.text


def test_hiding_needs_a_reason(world: World) -> None:
    created = post(world.browser("student"))
    first = reported(world.browser("faculty"), post_id=created["id"])
    for reason in (None, "   "):
        assert resolve(world.browser("admin"), first["id"], "HIDE", reason).status_code == 422
    assert resolve(world.browser("admin"), first["id"], "BAN").status_code == 422


def test_dismissing_keeps_the_post(world: World, conn: Connection) -> None:
    created = post(world.browser("student"))
    first = reported(world.browser("faculty"), post_id=created["id"])
    reported(world.browser("mech_student"), post_id=created["id"])
    response = resolve(world.browser("admin"), first["id"], "DISMISS", None)
    assert response.json() == {"action": "DISMISS", "closed_reports": 2}
    assert world.browser("faculty").get(f"{POSTS}/{created['id']}").json()["status"] == "VISIBLE"
    assert notifications(world.browser("student")) == []
    assert audit(conn, created["id"]) == [("community.reports_dismissed", None)]
    # A closed report doesn't block reporting it again later.
    reported(world.browser("faculty"), post_id=created["id"])


def test_hiding_a_comment(world: World, clock: Clock) -> None:
    created = post(world.browser("student"), "Lost my ID card")
    comments = f"{POSTS}/{created['id']}/comments"
    added = world.browser("mech_student").post(comments, {"body": WORDS}).json()
    first = reported(world.browser("student"), comment_id=added["id"])
    clock.advance(minutes=1)  # the queue is oldest first: keep the two reports apart in time
    on_post = reported(world.browser("faculty"), post_id=created["id"])
    item = queue(world.browser("admin"))[0]
    assert item["content"]["type"] == "comment" and item["content"]["body"] == WORDS
    hidden = resolve(world.browser("admin"), first["id"], "HIDE").json()
    assert hidden["closed_reports"] == 1
    # The report about the post itself stays open: it's about different content.
    assert [i["id"] for i in queue(world.browser("admin"))] == [on_post["id"]]
    assert world.browser("faculty").get(comments).json()["items"] == []
    assert world.browser("faculty").get(f"{POSTS}/{created['id']}").json()["comment_count"] == 0
    theirs = world.browser("mech_student").get(comments).json()["items"]
    assert [(c["status"], c["hidden_reason"]) for c in theirs] == [("HIDDEN", REASON)]
    [told] = notifications(world.browser("mech_student"))
    assert told["title"] == "A moderator hid your comment" and told["subject_id"] == created["id"]
    # The post itself is untouched, and the hidden comment can't be reported again.
    assert world.browser("faculty").get(f"{POSTS}/{created['id']}").json()["status"] == "VISIBLE"
    assert report(world.browser("faculty"), comment_id=added["id"]).status_code == 404


def test_deleted_content_leaves_the_queue(world: World) -> None:
    created = post(world.browser("student"))
    first = reported(world.browser("faculty"), post_id=created["id"])
    assert world.browser("student").send("DELETE", f"{POSTS}/{created['id']}").status_code == 204
    assert queue(world.browser("admin")) == []
    gone = resolve(world.browser("admin"), first["id"], "HIDE")
    assert gone.status_code == 409 and error_of(gone)["code"] == "content_deleted"
    assert resolve(world.browser("admin"), first["id"], "DISMISS", None).status_code == 200
