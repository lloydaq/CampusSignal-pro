"""Attendance (ACADEMIC-005…007, US-05, US-06): recording, the edit window, department-admin
corrections, the student's own summary, and the access matrix (PRD §11, ACADEMIC-010).

The test clock starts at 2026-10-21 12:00 UTC (17:30 in the colleges' Asia/Kolkata).
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from app.models import MembershipKind
from tests.integration.auth_helpers import error_of, scalar
from tests.integration.campus_world import CAMPUS, World, build_world
from tests.integration.conftest import Clock
from tests.integration.tenancy import add_member, make_user

pytestmark = pytest.mark.integration

SECTIONS = f"{CAMPUS}/sections"
SESSIONS = f"{CAMPUS}/attendance-sessions"
TODAY = "2026-10-21"
CLOSED = "Edit window closed — ask your department admin"


def ok(response: Any, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    return body


def not_found(response: Any) -> bool:
    return response.status_code == 404 and bool(error_of(response)["message"] == "Not found.")


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    world = build_world(session, app_factory())
    other = make_user(session, "other_faculty@northfield.example", name="Other Faculty")
    world.members["other_faculty"] = add_member(session, other, world.north, MembershipKind.FACULTY)
    session.commit()
    return world


@pytest.fixture
def cs(world: World) -> dict[str, Any]:
    """CS301 A in the current term, taught by `faculty`, with `student` and `mech_student`
    enrolled; and a MECH section taught by nobody."""
    admin = world.browser("admin")
    term = ok(
        admin.post(
            f"{CAMPUS}/terms",
            {
                "name": "2026-27 Odd",
                "starts_on": "2026-07-01",
                "ends_on": "2026-12-15",
                "is_current": True,
            },
        ),
        201,
    )

    def section(code: str, department: str) -> dict[str, Any]:
        subject = ok(
            admin.post(
                f"{CAMPUS}/subjects",
                {
                    "department_id": str(world.north.departments[department].id),
                    "code": code,
                    "name": code,
                },
            ),
            201,
        )
        return ok(
            admin.post(SECTIONS, {"term_id": term["id"], "subject_id": subject["id"], "name": "A"}),
            201,
        )

    cs301, me201 = section("CS301", "CSE"), section("ME201", "MECH")
    ok(
        admin.send(
            "PUT",
            f"{SECTIONS}/{cs301['id']}/instructors",
            {"membership_ids": [str(world.members["faculty"].id)]},
        )
    )
    ok(
        admin.post(
            f"{SECTIONS}/{cs301['id']}/enrollments/import", {"csv": "roll_number\nN-001\nN-002\n"}
        ),
        201,
    )
    ok(
        admin.post(f"{SECTIONS}/{me201['id']}/enrollments/import", {"csv": "roll_number\nN-002\n"}),
        201,
    )
    enrollments = ok(admin.get(f"{SECTIONS}/{cs301['id']}/enrollments"))["items"]
    by_name = {e["display_name"]: e["id"] for e in enrollments}
    return {
        "term": term,
        "section": cs301,
        "mech": me201,
        "student": by_name["Student"],
        "mech_student": by_name["Mech Student"],
    }


def marks(
    cs: dict[str, Any], student: str = "PRESENT", mech: str = "PRESENT"
) -> list[dict[str, str]]:
    return [
        {"enrollment_id": cs["student"], "status": student},
        {"enrollment_id": cs["mech_student"], "status": mech},
    ]


def record(world: World, cs: dict[str, Any], who: str = "faculty", **body: Any) -> Any:
    payload = {"held_on": TODAY, "slot": 1, "records": marks(cs)} | body
    return world.browser(who).post(f"{SECTIONS}/{cs['section']['id']}/attendance-sessions", payload)


# --- recording (ACADEMIC-005) --------------------------------------------------------------


def test_assigned_faculty_record_a_session(
    world: World, cs: dict[str, Any], conn: Connection
) -> None:
    body = ok(record(world, cs, records=marks(cs, mech="ABSENT")), 201)
    assert (body["held_on"], body["slot"], body["version"]) == (TODAY, 1, 1)
    assert body["counts"] == {"present": 1, "absent": 1, "excused": 0}
    assert body["recorded_by"]["display_name"] == "Faculty"
    assert body["edit"] == "faculty"
    assert body["edit_window_closes_at"] == "2026-10-23T12:00:00Z"
    assert [(r["display_name"], r["status"]) for r in body["records"]] == [
        ("Mech Student", "ABSENT"),
        ("Student", "PRESENT"),
    ]
    # Audited with counts only; no notification carries attendance (US-08 rule, PRD §17).
    data = conn.exec_driver_sql(
        "SELECT metadata::text FROM audit_log WHERE action = 'academic.attendance_recorded'"
    ).scalar_one()
    assert "PRESENT" not in data and "ABSENT" not in data
    assert scalar(conn, "SELECT count(*) FROM notifications") == 0

    listed = ok(
        world.browser("dept_admin").get(f"{SECTIONS}/{cs['section']['id']}/attendance-sessions")
    )
    assert [s["id"] for s in listed["items"]] == [body["id"]]
    assert listed["items"][0]["edit"] == "correction"
    assert ok(world.browser("admin").get(f"{SESSIONS}/{body['id']}"))["edit"] is None


def test_one_session_per_section_date_and_slot(world: World, cs: dict[str, Any]) -> None:
    """US-06: a second session for the same section/date/slot → 409."""
    ok(record(world, cs), 201)
    again = record(world, cs)
    assert again.status_code == 409
    assert error_of(again)["code"] == "session_exists"
    ok(record(world, cs, slot=2), 201)
    ok(record(world, cs, held_on="2026-10-20"), 201)


def test_dates_must_be_in_the_term_and_not_in_the_future(world: World, cs: dict[str, Any]) -> None:
    for held_on in ("2026-10-22", "2026-06-30", "2026-12-16"):
        response = record(world, cs, held_on=held_on)
        assert response.status_code == 422, held_on
        assert error_of(response)["details"][0]["field"] == "held_on"
    assert record(world, cs, slot=13).status_code == 422
    assert record(world, cs, slot=0).status_code == 422


def test_the_future_is_judged_in_the_colleges_timezone(
    world: World, cs: dict[str, Any], clock: Clock
) -> None:
    clock.advance(hours=7)  # 19:00 UTC on the 21st is 00:30 on the 22nd in Asia/Kolkata
    ok(record(world, cs, held_on="2026-10-22"), 201)


def test_every_enrolled_student_is_marked_exactly_once(world: World, cs: dict[str, Any]) -> None:
    missing = record(world, cs, records=marks(cs)[:1])
    assert missing.status_code == 422
    assert "1 missing" in error_of(missing)["details"][0]["message"]
    twice = record(world, cs, records=marks(cs) + marks(cs)[:1])
    assert [d["field"] for d in error_of(twice)["details"]] == ["records.2.enrollment_id"]
    other = ok(world.browser("admin").get(f"{SECTIONS}/{cs['mech']['id']}/enrollments"))["items"][
        0
    ]["id"]
    stranger = record(
        world, cs, records=[*marks(cs), {"enrollment_id": other, "status": "PRESENT"}]
    )
    assert [d["field"] for d in error_of(stranger)["details"]] == ["records.2.enrollment_id"]
    bad_status = record(world, cs, records=marks(cs, student="LATE"))
    assert bad_status.status_code == 422


def test_who_may_record(world: World, cs: dict[str, Any]) -> None:
    """US-06: faculty not assigned → 404; readers who may not record → 403."""
    assert not_found(record(world, cs, "other_faculty"))
    for who in ("dept_admin", "admin", "student"):
        response = record(world, cs, who)
        assert response.status_code == 403, who
    mech = world.browser("dept_admin").post(
        f"{SECTIONS}/{cs['mech']['id']}/attendance-sessions",
        {"held_on": TODAY, "slot": 1, "records": []},
    )
    assert mech.status_code == 422  # an empty list is rejected before anything is looked up
    mech = world.browser("dept_admin").post(
        f"{SECTIONS}/{cs['mech']['id']}/attendance-sessions",
        {"held_on": TODAY, "slot": 1, "records": marks(cs)},
    )
    assert not_found(mech)


def test_who_may_read(world: World, cs: dict[str, Any]) -> None:
    session = ok(record(world, cs), 201)
    for who in ("faculty", "dept_admin", "admin"):
        ok(world.browser(who).get(f"{SESSIONS}/{session['id']}"))
        ok(world.browser(who).get(f"{SECTIONS}/{cs['section']['id']}/attendance-sessions"))
    assert not_found(world.browser("other_faculty").get(f"{SESSIONS}/{session['id']}"))
    for who in ("student", "mech_student"):
        response = world.browser(who).get(f"{SESSIONS}/{session['id']}")
        assert response.status_code == 403
        assert "Mech Student" not in response.text


# --- editing (ACADEMIC-006) ----------------------------------------------------------------


def edit(world: World, who: str, session: dict[str, Any], **body: Any) -> Any:
    return world.browser(who).patch(
        f"{SESSIONS}/{session['id']}", {"version": session["version"]} | body
    )


def test_faculty_edit_inside_the_window_only(
    world: World, cs: dict[str, Any], clock: Clock, conn: Connection
) -> None:
    """US-06: faculty edit after 48 h → 403 "Edit window closed — ask your department admin"."""
    session = ok(record(world, cs), 201)
    clock.advance(hours=47)
    edited = ok(
        edit(
            world,
            "faculty",
            session,
            records=[{"enrollment_id": cs["student"], "status": "EXCUSED"}],
        )
    )
    assert edited["version"] == 2
    assert edited["counts"] == {"present": 1, "absent": 0, "excused": 1}
    entry = conn.exec_driver_sql(
        "SELECT reason, metadata->>'mode' FROM audit_log "
        "WHERE action = 'academic.attendance_edited'"
    ).one()
    assert entry == (None, "faculty")

    clock.advance(hours=1)
    late = edit(
        world, "faculty", edited, records=[{"enrollment_id": cs["student"], "status": "PRESENT"}]
    )
    assert late.status_code == 403
    assert (error_of(late)["code"], error_of(late)["message"]) == ("edit_window_closed", CLOSED)
    assert (
        ok(world.browser("faculty").get(f"{SESSIONS}/{session['id']}"))["edit"] == "window_closed"
    )


def test_department_admin_corrections_need_a_reason_and_are_audited(
    world: World, cs: dict[str, Any], clock: Clock, conn: Connection
) -> None:
    """US-06: dept admin edit without reason → 422; with reason → audit has old/new status."""
    session = ok(record(world, cs, records=marks(cs, mech="ABSENT")), 201)
    clock.advance(days=10)
    change = [{"enrollment_id": cs["mech_student"], "status": "PRESENT"}]
    missing = edit(world, "dept_admin", session, records=change)
    assert missing.status_code == 422
    assert error_of(missing)["details"][0]["field"] == "reason"
    assert edit(world, "dept_admin", session, records=change, reason="   ").status_code == 422

    fixed = ok(
        edit(world, "dept_admin", session, records=change, reason="Medical certificate shown")
    )
    assert fixed["counts"]["absent"] == 0
    reason, mode, changes, actor = conn.exec_driver_sql(
        "SELECT a.reason, a.metadata->>'mode', a.metadata->'changes', u.display_name "
        "FROM audit_log a JOIN users u ON u.id = a.actor_user_id "
        "WHERE a.action = 'academic.attendance_edited'"
    ).one()
    assert (reason, mode, actor) == ("Medical certificate shown", "correction", "Dept Admin")
    assert changes == [{"enrollment_id": cs["mech_student"], "from": "ABSENT", "to": "PRESENT"}]


def test_edits_check_the_version_and_the_marks(world: World, cs: dict[str, Any]) -> None:
    session = ok(record(world, cs), 201)
    change = [{"enrollment_id": cs["student"], "status": "ABSENT"}]
    ok(edit(world, "faculty", session, records=change))
    stale = edit(world, "faculty", session, records=change)
    assert stale.status_code == 409
    assert error_of(stale)["code"] == "version_conflict"
    current = ok(world.browser("faculty").get(f"{SESSIONS}/{session['id']}"))
    other = ok(world.browser("admin").get(f"{SECTIONS}/{cs['mech']['id']}/enrollments"))["items"][
        0
    ]["id"]
    stranger = edit(
        world, "faculty", current, records=[{"enrollment_id": other, "status": "ABSENT"}]
    )
    assert stranger.status_code == 422
    unchanged = ok(edit(world, "faculty", current, records=change))
    assert unchanged["version"] == current["version"]  # nothing changed, nothing bumped


def test_who_may_not_edit(world: World, cs: dict[str, Any]) -> None:
    session = ok(record(world, cs), 201)
    change = [{"enrollment_id": cs["student"], "status": "ABSENT"}]
    assert edit(world, "admin", session, records=change, reason="x").status_code == 403
    assert edit(world, "student", session, records=change).status_code == 403
    assert not_found(edit(world, "other_faculty", session, records=change))


# --- the student's own attendance (ACADEMIC-007, US-05) ------------------------------------


def test_students_see_their_own_summary(world: World, cs: dict[str, Any]) -> None:
    """US-05: one row per enrolled subject, matching the recorded sessions."""
    ok(
        record(
            world, cs, held_on="2026-10-19", records=marks(cs, student="PRESENT", mech="ABSENT")
        ),
        201,
    )
    ok(
        record(world, cs, held_on="2026-10-20", records=marks(cs, student="ABSENT", mech="ABSENT")),
        201,
    )
    ok(
        record(
            world, cs, held_on="2026-10-21", records=marks(cs, student="EXCUSED", mech="PRESENT")
        ),
        201,
    )

    mine = ok(world.browser("student").get(f"{CAMPUS}/me/attendance"))
    assert mine["term"]["id"] == cs["term"]["id"]
    assert [
        (i["subject"]["code"], i["held"], i["attended"], i["excused"], i["percentage"])
        for i in mine["items"]
    ] == [("CS301", 3, 1, 1, 50.0)]
    theirs = ok(world.browser("mech_student").get(f"{CAMPUS}/me/attendance"))
    assert [(i["subject"]["code"], i["held"], i["percentage"]) for i in theirs["items"]] == [
        ("CS301", 3, 33.3),
        ("ME201", 0, None),
    ]

    detail = ok(world.browser("student").get(f"{CAMPUS}/me/attendance/{cs['section']['id']}"))
    assert (detail["held"], detail["attended"], detail["percentage"]) == (3, 1, 50.0)
    assert [(s["held_on"], s["status"]) for s in detail["sessions"]] == [
        ("2026-10-21", "EXCUSED"),
        ("2026-10-20", "ABSENT"),
        ("2026-10-19", "PRESENT"),
    ]
    assert "Mech Student" not in str(detail)


def test_with_no_sessions_the_summary_is_empty(world: World, cs: dict[str, Any]) -> None:
    """US-05: the screen says "No attendance has been recorded for this term yet." from this."""
    mine = ok(world.browser("student").get(f"{CAMPUS}/me/attendance"))
    assert [(i["held"], i["percentage"]) for i in mine["items"]] == [(0, None)]


def test_another_students_attendance_is_not_found(world: World, cs: dict[str, Any]) -> None:
    """US-05: requesting another student's attendance by any ID → 404."""
    ok(record(world, cs), 201)
    student = world.browser("student")
    for other_id in (cs["mech"]["id"], cs["mech_student"], cs["student"]):
        assert not_found(student.get(f"{CAMPUS}/me/attendance/{other_id}"))
    for who in ("faculty", "admin"):
        assert world.browser(who).get(f"{CAMPUS}/me/attendance").status_code == 403
        assert (
            world.browser(who).get(f"{CAMPUS}/me/attendance/{cs['section']['id']}").status_code
            == 403
        )


# --- what attendance blocks ----------------------------------------------------------------


def test_an_enrollment_with_attendance_cannot_be_removed(world: World, cs: dict[str, Any]) -> None:
    ok(record(world, cs), 201)
    removed = world.browser("admin").send("DELETE", f"{CAMPUS}/enrollments/{cs['student']}")
    assert removed.status_code == 409
    assert error_of(removed)["code"] == "enrollment_has_records"


def test_term_dates_cannot_leave_attendance_outside(world: World, cs: dict[str, Any]) -> None:
    ok(record(world, cs, held_on="2026-10-01"), 201)
    path = f"{CAMPUS}/terms/{cs['term']['id']}"
    admin = world.browser("admin")
    blocked = admin.patch(path, {"starts_on": "2026-10-02"})
    assert blocked.status_code == 409
    assert error_of(blocked)["code"] == "term_has_sessions_outside"
    assert admin.patch(path, {"ends_on": "2026-09-30"}).status_code == 409
    ok(admin.patch(path, {"starts_on": "2026-10-01", "ends_on": "2026-12-31"}))
