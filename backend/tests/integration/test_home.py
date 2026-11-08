# ruff: noqa: F811  (fixtures imported from test_attendance are redefined as parameters)
"""The role-aware home (HOME-001…004, US-16) and the display name (PROFILE-001).

Reuses the attendance world: CS301 A taught by `faculty`, `student` and `mech_student` enrolled.
The clock starts on Wednesday 2026-10-21 at 12:00 UTC, 17:30 in the colleges' Asia/Kolkata.
"""

from typing import Any

import pytest

from app.services import attendance as attendance_service
from tests.integration.campus_world import CAMPUS, World
from tests.integration.test_attendance import cs, ok, world  # noqa: F401

pytestmark = pytest.mark.integration

HOME = f"{CAMPUS}/home"
ISSUE = {
    "category": "CLASSROOM_EQUIPMENT",
    "title": "Projector in C-103 flickers",
    "description": "Every few seconds.",
    "location": "Block C",
}


def home(world: World, who: str) -> dict[str, Any]:
    return ok(world.browser(who).get(HOME))


def schedule(world: World, cs: dict[str, Any], weekday: int, starts: str, ends: str) -> None:
    ok(
        world.browser("admin").post(
            f"{CAMPUS}/sections/{cs['section']['id']}/timetable",
            {"weekday": weekday, "starts_at": starts, "ends_at": ends, "room": "C-103"},
        ),
        201,
    )


def test_a_students_home(world: World, cs: dict[str, Any]) -> None:
    """HOME-001: today's classes, attendance per subject, own open issues; no queues (US-16)."""
    schedule(world, cs, 3, "09:00", "10:00")  # Wednesday: today
    schedule(world, cs, 4, "09:00", "10:00")  # Thursday: not today
    ok(world.browser("student").post(f"{CAMPUS}/issues", ISSUE), 201)
    body = home(world, "student")
    assert body["today"] == "2026-10-21" and body["is_demo"] is False
    assert body["classes"]["status"] == "ok"
    assert [(c["subject"]["code"], c["starts_at"]) for c in body["classes"]["items"]] == [
        ("CS301", "09:00:00")
    ]
    assert [(a["subject"]["code"], a["held"]) for a in body["attendance"]["items"]] == [
        ("CS301", 0)
    ]
    assert body["my_issues"]["open_count"] == 1
    assert body["my_issues"]["items"][0]["title"] == "Projector in C-103 flickers"
    assert body["queues"] is None and body["needs_attendance"] is None
    # Another student's issue isn't theirs.
    assert home(world, "mech_student")["my_issues"]["open_count"] == 0


def test_a_faculty_members_home(world: World, cs: dict[str, Any], clock: Any) -> None:
    """HOME-002: their sections' classes today, and classes in the last 7 days with no
    attendance recorded (only those already over)."""
    schedule(world, cs, 1, "09:00", "10:00")  # Monday 19th
    schedule(world, cs, 3, "09:00", "10:00")  # Wednesday 21st, over by 17:30
    schedule(world, cs, 3, "18:00", "19:00")  # Wednesday 21st, not over yet
    body = home(world, "faculty")
    assert [c["starts_at"] for c in body["classes"]["items"]] == ["09:00:00", "18:00:00"]
    missing = [(m["held_on"], m["starts_at"]) for m in body["needs_attendance"]["items"]]
    # The 7 days are Thursday the 15th to Wednesday the 21st, so last Wednesday (the 14th) is
    # too old; this evening's 18:00 class isn't over yet, but the morning one is. Newest first.
    assert missing == [("2026-10-21", "09:00:00"), ("2026-10-19", "09:00:00")]
    assert body["attendance"] is None and body["queues"] is None

    # Recording the Monday class clears it.
    ok(
        world.browser("faculty").post(
            f"{CAMPUS}/sections/{cs['section']['id']}/attendance-sessions",
            {
                "held_on": "2026-10-19",
                "slot": 1,
                "records": [
                    {"enrollment_id": cs["student"], "status": "PRESENT"},
                    {"enrollment_id": cs["mech_student"], "status": "PRESENT"},
                ],
            },
        ),
        201,
    )
    after = [m["held_on"] for m in home(world, "faculty")["needs_attendance"]["items"]]
    assert "2026-10-19" not in after and "2026-10-21" in after
    # Faculty not assigned to the section see nothing of it.
    other = home(world, "other_faculty")
    assert other["classes"]["items"] == [] and other["needs_attendance"]["items"] == []


def test_admin_queues_are_only_the_ones_the_viewer_acts_on(
    world: World, cs: dict[str, Any]
) -> None:
    """HOME-003, US-16: counts and only the viewer's queues; other colleges' work never counts."""
    ok(world.browser("student").post(f"{CAMPUS}/issues", ISSUE), 201)
    post = ok(
        world.browser("student").post(
            f"{CAMPUS}/posts", {"body": "Rumour", "visibility": "COLLEGE"}
        ),
        201,
    )
    ok(
        world.browser("mech_student").post(
            f"{CAMPUS}/reports", {"post_id": post["id"], "reason": "SPAM"}
        ),
        201,
    )

    def queues(who: str) -> dict[str, int] | None:
        block = home(world, who)["queues"]
        return None if block is None else {q["kind"]: q["count"] for q in block["items"]}

    assert queues("admin") == {
        "membership_requests": 0,
        "content_reports": 1,
        "unacknowledged_issues": 1,
    }
    # A CSE department admin: requests and reports (a college post isn't theirs), no issues.
    assert queues("dept_admin") == {"membership_requests": 0, "content_reports": 0}
    for who in ("student", "faculty"):
        assert queues(who) is None, who
    assert queues("river_admin") == {
        "membership_requests": 0,
        "content_reports": 0,
        "unacknowledged_issues": 0,
    }


def test_a_failing_block_leaves_the_others(
    world: World, cs: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """US-16: a failing block does not hide other blocks."""

    def broken(*_: Any) -> Any:
        raise RuntimeError("attendance is down")

    monkeypatch.setattr(attendance_service, "my_attendance", broken)
    body = home(world, "student")
    assert body["attendance"] == {"status": "error", "term": None, "items": []}
    assert body["classes"]["status"] == "ok" and body["my_issues"]["status"] == "ok"


def test_the_home_needs_a_campus(world: World) -> None:
    response = world.browser("river_student").get(HOME)
    assert response.status_code == 200  # their own college's home
    assert "CS301" not in response.text and "Projector" not in response.text


# --- the display name (PROFILE-001) --------------------------------------------------------


def test_changing_the_display_name(world: World) -> None:
    student = world.browser("student")
    assert student.patch("/api/v1/me", {"display_name": "x" * 61}).status_code == 422  # US-16
    assert student.patch("/api/v1/me", {"display_name": "   "}).status_code == 422
    assert student.patch("/api/v1/me", {"display_name": "A", "email": "x@y"}).status_code == 422
    changed = ok(student.patch("/api/v1/me", {"display_name": "  Ishita   Verma "}))
    assert changed["display_name"] == "Ishita Verma"
    assert ok(student.get("/api/v1/me"))["user"]["display_name"] == "Ishita Verma"
