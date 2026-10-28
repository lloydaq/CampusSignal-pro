"""Campus issues, handling them (ISSUE-002, 004, 005, 006, 008; US-09, J9): status changes by the
PRD §9.8.1 table, reopen limits, duplicates, assignment and the assignee picker, comments, and
what the reporter and the assignee are told."""

import uuid
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from app.models import MembershipKind, MembershipStatus, Role
from tests.integration.auth_helpers import error_of
from tests.integration.campus_world import World, build_world
from tests.integration.conftest import Clock
from tests.integration.platform_helpers import Browser
from tests.integration.tenancy import add_member, make_user
from tests.integration.test_issues import ISSUES, NO_SUCH_ISSUE, SECRET, not_found, report

pytestmark = pytest.mark.integration

NOTIFICATIONS = "/api/v1/me/notifications"
ASSIGNEES = "/api/v1/campus/assignees"
INTERNAL = "Vendor quote is 40k, wait for budget"  # an internal note the reporter never sees


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    world = build_world(session, app_factory())
    for who, kind in (("coordinator", MembershipKind.STAFF), ("staff", MembershipKind.STAFF)):
        user = make_user(session, f"{who}@northfield.example", name=who.title())
        roles = ((Role.ISSUE_COORDINATOR, None),) if who == "coordinator" else ()
        world.members[who] = add_member(
            session, user, world.north, kind, department=None, roles=roles
        )
    session.commit()
    return world


def move(who: Browser, issue: dict[str, Any], to: str, **extra: Any) -> httpx2.Response:
    return who.post(
        f"{ISSUES}/{issue['id']}/transitions",
        {"to_status": to, "version": issue["version"], **extra},
    )


def moved(who: Browser, issue: dict[str, Any], to: str, **extra: Any) -> dict[str, Any]:
    response = move(who, issue, to, **extra)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    assert result["status"] == to
    return result


def assign(who: Browser, issue: dict[str, Any], assignee: uuid.UUID | None) -> httpx2.Response:
    return who.post(
        f"{ISSUES}/{issue['id']}/assignment",
        {"assignee_id": str(assignee) if assignee else None, "version": issue["version"]},
    )


def comment(
    who: Browser, issue: dict[str, Any], text: str, internal: bool = False
) -> httpx2.Response:
    return who.post(f"{ISSUES}/{issue['id']}/updates", {"body": text, "is_internal": internal})


def refused(response: httpx2.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert error_of(response)["code"] == code
    assert SECRET not in response.text


def told(who: Browser) -> list[tuple[str, str]]:
    items = who.get(NOTIFICATIONS).json()["items"]
    return [(n["type"], n["title"]) for n in reversed(items)]


def audit(conn: Connection, issue: dict[str, Any]) -> list[tuple[str, str | None, str]]:
    rows = conn.exec_driver_sql(
        "SELECT action, reason, metadata::text FROM audit_log "
        "WHERE target_id = %s ORDER BY created_at",
        (issue["id"],),
    ).all()
    return [(a, r, m) for a, r, m in rows]


def acknowledged(world: World) -> dict[str, Any]:
    return moved(world.browser("coordinator"), report(world.browser("student")), "ACKNOWLEDGED")


def resolved(world: World) -> dict[str, Any]:
    issue = moved(world.browser("coordinator"), acknowledged(world), "IN_PROGRESS")
    return moved(world.browser("coordinator"), issue, "RESOLVED", note="Replaced the projector.")


# --- the whole journey (J9) ---


def test_a_coordinator_handles_an_issue_end_to_end(
    world: World, conn: Connection, clock: Clock
) -> None:
    coordinator, faculty, student = (
        world.browser(w) for w in ("coordinator", "faculty", "student")
    )
    issue = report(student)
    issue = moved(coordinator, issue, "ACKNOWLEDGED")
    clock.advance(minutes=1)  # notifications list newest first: keep the steps apart in time
    response = assign(coordinator, issue, world.members["faculty"].id)
    assert response.status_code == 200, response.text
    issue = response.json()
    assert issue["assignee_name"] == "Faculty"
    # The assignee now finds it under "Assigned to me" and moves it on.
    assert [i["id"] for i in faculty.get(f"{ISSUES}?scope=assigned").json()["items"]] == [
        issue["id"]
    ]
    clock.advance(minutes=1)
    issue = moved(faculty, faculty.get(f"{ISSUES}/{issue['id']}").json(), "IN_PROGRESS")
    clock.advance(hours=3)
    issue = moved(faculty, issue, "RESOLVED", note="Replaced the projector.")
    assert issue["resolved_at"].startswith("2026-10-21T15:02:00")
    assert issue["version"] == 5

    timeline = [
        (u["kind"], u["from_status"], u["to_status"], u["actor_name"], u["assignee_name"])
        for u in student.get(f"{ISSUES}/{issue['id']}").json()["updates"]
    ]
    assert timeline == [
        ("CREATED", None, None, "Student", None),
        ("STATUS", "SUBMITTED", "ACKNOWLEDGED", "Coordinator", None),
        ("ASSIGNMENT", None, None, "Coordinator", "Faculty"),
        ("STATUS", "ACKNOWLEDGED", "IN_PROGRESS", "Faculty", None),
        ("STATUS", "IN_PROGRESS", "RESOLVED", "Faculty", None),
    ]
    # ISSUE-008: the reporter hears of every status change; the assignee of the assignment.
    assert told(student) == [
        ("ISSUE_STATUS_CHANGED", f"Issue acknowledged: {SECRET}"),
        ("ISSUE_STATUS_CHANGED", f"Issue in progress: {SECRET}"),
        ("ISSUE_STATUS_CHANGED", f"Issue resolved: {SECRET}"),
    ]
    assert told(faculty) == [("ISSUE_ASSIGNED", f"Issue assigned to you: {SECRET}")]
    assert {n["subject_id"] for n in student.get(NOTIFICATIONS).json()["items"]} == {issue["id"]}
    assert told(coordinator) == []  # nobody is told about their own change
    assert [(a, r) for a, r, _ in audit(conn, issue)] == [
        ("issue.created", None),
        ("issue.status_changed", None),
        ("issue.assigned", None),
        ("issue.status_changed", None),
        ("issue.status_changed", None),  # a resolution note isn't a reason
    ]
    assert all("projector" not in m for _, _, m in audit(conn, issue))


# --- the transition table over HTTP (ISSUE-002, US-09) ---


def test_the_assignee_cannot_skip_acknowledgement(world: World) -> None:  # US-09
    issue = report(world.browser("student"))
    issue = assign(world.browser("coordinator"), issue, world.members["faculty"].id).json()
    refused(move(world.browser("faculty"), issue, "IN_PROGRESS"), 409, "invalid_transition")


def test_resolving_needs_a_note(world: World) -> None:  # US-09
    coordinator = world.browser("coordinator")
    issue = moved(coordinator, acknowledged(world), "IN_PROGRESS")
    response = move(coordinator, issue, "RESOLVED")
    refused(response, 422, "validation_error")
    assert error_of(response)["details"] == [
        {"field": "note", "message": "Add a note to explain this change."}
    ]
    assert move(coordinator, issue, "RESOLVED", note="   ").status_code == 422


def test_only_the_handling_side_moves_an_issue(world: World) -> None:
    issue = report(world.browser("student"))
    # The reporter can read it, so they hear "not allowed"; others don't learn it exists.
    refused(move(world.browser("student"), issue, "ACKNOWLEDGED"), 403, "forbidden")
    for who in ("faculty", "dept_admin", "mech_student", "river_admin"):
        not_found(move(world.browser(who), issue, "ACKNOWLEDGED"))
    not_found(
        world.browser("coordinator").post(
            f"{NO_SUCH_ISSUE}/transitions", {"to_status": "ACKNOWLEDGED", "version": 1}
        )
    )
    # College admins hold every coordinator power.
    moved(world.browser("admin"), issue, "ACKNOWLEDGED")


def test_a_stale_version_is_a_conflict(world: World) -> None:
    issue = report(world.browser("student"))
    moved(world.browser("coordinator"), issue, "ACKNOWLEDGED")
    response = move(world.browser("admin"), issue, "REJECTED", note="Not ours.")  # version 1
    refused(response, 409, "version_conflict")
    assert world.browser("admin").get(f"{ISSUES}/{issue['id']}").json()["status"] == "ACKNOWLEDGED"


@pytest.mark.parametrize(
    "extra",
    [
        {"status": "RESOLVED"},
        {"college_id": "00000000-0000-4000-8000-000000000000"},
        {"resolved_at": "2026-10-21T12:00:00Z"},
        {"version": 0},
    ],
)
def test_transition_bodies_are_strict(world: World, extra: dict[str, Any]) -> None:
    issue = report(world.browser("student"))
    response = move(world.browser("coordinator"), issue, "ACKNOWLEDGED", **extra)
    assert response.status_code == 422, response.text


def test_rejecting_needs_a_reason_the_reporter_sees(world: World, conn: Connection) -> None:
    coordinator = world.browser("coordinator")
    issue = report(world.browser("student"))
    refused(move(coordinator, issue, "REJECTED"), 422, "validation_error")
    issue = moved(coordinator, issue, "REJECTED", note="This is the city's road, not ours.")
    as_reporter = world.browser("student").get(f"{ISSUES}/{issue['id']}").json()
    assert as_reporter["updates"][-1]["body"] == "This is the city's road, not ours."
    assert told(world.browser("student")) == [
        ("ISSUE_STATUS_CHANGED", f"Issue closed without action: {SECRET}")
    ]
    assert audit(conn, issue)[-1][:2] == (
        "issue.status_changed",
        "This is the city's road, not ours.",
    )


# --- reopening ---


def test_the_reporter_reopens_twice_within_14_days(
    world: World, conn: Connection, clock: Clock
) -> None:
    issue = resolved(world)
    refused(move(world.browser("student"), issue, "ACKNOWLEDGED"), 422, "validation_error")
    for _ in range(2):
        clock.advance(days=13)  # sessions lapse over such gaps: sign in afresh
        student, coordinator = world.browser("student"), world.browser("coordinator")
        issue = moved(student, issue, "ACKNOWLEDGED", note="Still sparks.")
        assert issue["resolved_at"] is None
        issue = moved(coordinator, issue, "IN_PROGRESS")
        issue = moved(coordinator, issue, "RESOLVED", note="Fixed again.")
    refused(move(student, issue, "ACKNOWLEDGED", note="Again."), 409, "reopen_limit_reached")
    # A coordinator still reopens anytime.
    clock.advance(days=60)
    student, coordinator = world.browser("student"), world.browser("coordinator")
    issue = moved(coordinator, issue, "ACKNOWLEDGED", note="Reported in person.")
    titles = [t for _, t in told(student)]
    assert titles.count(f"Issue reopened: {SECRET}") == 1  # the reporter's own aren't told
    reopen = audit(conn, issue)[-1]
    assert reopen[:2] == ("issue.status_changed", "Reported in person.")


def test_the_reopen_window_closes_after_14_days(world: World, clock: Clock) -> None:
    issue = resolved(world)
    clock.advance(days=14)
    refused(
        move(world.browser("student"), issue, "ACKNOWLEDGED", note="Back."),
        409,
        "reopen_window_closed",
    )
    moved(world.browser("admin"), issue, "ACKNOWLEDGED", note="Back.")  # owner, 2026-10-25


def test_a_rejection_is_reopened_by_staff_only(world: World) -> None:
    issue = moved(
        world.browser("coordinator"), report(world.browser("student")), "REJECTED", note="No."
    )
    refused(move(world.browser("student"), issue, "ACKNOWLEDGED", note="Please."), 403, "forbidden")
    moved(world.browser("coordinator"), issue, "ACKNOWLEDGED", note="Looked again.")


# --- duplicates (ISSUE-006) ---


def test_marking_a_duplicate(world: World, conn: Connection, clock: Clock) -> None:
    coordinator = world.browser("coordinator")
    original = report(world.browser("mech_student"), title="Original secret title")
    copy = report(world.browser("student"))
    copy = moved(coordinator, copy, "REJECTED", duplicate_of_id=original["id"])  # link = reason
    assert copy["duplicate_of"]["id"] == original["id"]

    as_reporter = world.browser("student").get(f"{ISSUES}/{copy['id']}")
    assert as_reporter.json()["duplicate_of"] == {
        "id": None,
        "status": "SUBMITTED",
        "resolved_at": None,
    }
    for leak in ("Original secret title", "Mech Student", original["id"]):
        assert leak not in as_reporter.text, leak
    assert told(world.browser("student")) == [
        ("ISSUE_STATUS_CHANGED", f"Issue closed as a duplicate: {SECRET}")
    ]
    assert f'"duplicate_of": "{original["id"]}"' in audit(conn, copy)[-1][2]

    # The duplicate's reporter follows the original's progress, still status only.
    original = moved(coordinator, original, "ACKNOWLEDGED")
    original = moved(coordinator, original, "IN_PROGRESS")
    moved(coordinator, original, "RESOLVED", note="Original secret resolution")
    as_reporter = world.browser("student").get(f"{ISSUES}/{copy['id']}")
    assert as_reporter.json()["duplicate_of"]["status"] == "RESOLVED"
    assert "Original secret" not in as_reporter.text

    # Reopening the duplicate clears its link (owner, 2026-10-25).
    reopened = moved(coordinator, copy, "ACKNOWLEDGED", note="Different room after all.")
    assert reopened["duplicate_of"] is None


@pytest.fixture
def river_issue_id(world: World) -> str:
    reported = world.browser("river_student").post(
        ISSUES,
        {
            "category": "OTHER",
            "title": "Riverside taps",
            "description": "Dry.",
            "location": "Riverside hostel",
        },
    )
    assert reported.status_code == 201, reported.text
    issue_id: str = reported.json()["id"]
    return issue_id


def test_duplicate_links_are_checked(world: World, river_issue_id: str) -> None:
    coordinator = world.browser("coordinator")
    first, second, third = (report(world.browser("student"), title=t) for t in "ABC")
    refused(
        move(coordinator, first, "ACKNOWLEDGED", duplicate_of_id=second["id"]),
        422,
        "validation_error",
    )
    refused(
        move(coordinator, first, "REJECTED", duplicate_of_id=first["id"]), 422, "validation_error"
    )
    not_found(move(coordinator, first, "REJECTED", duplicate_of_id=river_issue_id))
    not_found(move(coordinator, first, "REJECTED", duplicate_of_id=NO_SUCH_ISSUE.rsplit("/", 1)[1]))
    moved(coordinator, second, "REJECTED", duplicate_of_id=third["id"])
    response = move(coordinator, first, "REJECTED", duplicate_of_id=second["id"])  # no chains
    refused(response, 422, "validation_error")
    assert error_of(response)["details"][0]["field"] == "duplicate_of_id"


# --- assignment (ISSUE-004, US-09) ---


def test_assigning_to_another_college_is_not_found(world: World) -> None:  # US-09
    issue = report(world.browser("student"))
    not_found(assign(world.browser("coordinator"), issue, world.members["river_admin"].id))
    not_found(assign(world.browser("coordinator"), issue, uuid.uuid4()))
    detail = world.browser("coordinator").get(f"{ISSUES}/{issue['id']}").json()
    assert detail["assignee_name"] is None and detail["version"] == 1


def test_only_active_faculty_and_staff_can_be_assigned(world: World, session: Session) -> None:
    issue = report(world.browser("student"))
    coordinator = world.browser("coordinator")
    response = assign(coordinator, issue, world.members["mech_student"].id)
    refused(response, 422, "validation_error")
    assert error_of(response)["details"][0]["field"] == "assignee_id"
    world.members["staff"].status = MembershipStatus.SUSPENDED
    session.commit()
    refused(assign(coordinator, issue, world.members["staff"].id), 422, "validation_error")


def test_only_coordinators_and_college_admins_assign(world: World) -> None:
    issue = report(world.browser("student"))
    issue = assign(world.browser("admin"), issue, world.members["faculty"].id).json()
    # The assignee and the reporter read the issue but can't hand it on.
    for who in ("faculty", "student"):
        refused(assign(world.browser(who), issue, world.members["staff"].id), 403, "forbidden")
    for who in ("dept_admin", "mech_student", "river_admin"):
        not_found(assign(world.browser(who), issue, world.members["staff"].id))


def test_reassigning_and_unassigning(world: World, conn: Connection) -> None:
    coordinator = world.browser("coordinator")
    issue = report(world.browser("student"))
    issue = assign(coordinator, issue, world.members["faculty"].id).json()
    same = assign(coordinator, issue, world.members["faculty"].id).json()
    assert same["version"] == issue["version"]  # assigning the same person changes nothing
    issue = assign(coordinator, issue, world.members["staff"].id).json()
    not_found(world.browser("faculty").get(f"{ISSUES}/{issue['id']}"))  # no longer theirs
    assert told(world.browser("staff")) == [("ISSUE_ASSIGNED", f"Issue assigned to you: {SECRET}")]
    issue = assign(coordinator, issue, None).json()
    assert issue["assignee_name"] is None
    assignments = [u["assignee_name"] for u in issue["updates"] if u["kind"] == "ASSIGNMENT"]
    assert assignments == ["Faculty", "Staff", None]
    assert [a for a, _, _ in audit(conn, issue)].count("issue.assigned") == 3
    refused(assign(coordinator, {**issue, "version": 1}, None), 409, "version_conflict")


def test_closed_issues_are_not_assigned(world: World) -> None:
    coordinator = world.browser("coordinator")
    issue = moved(coordinator, report(world.browser("student")), "REJECTED", note="No.")
    refused(assign(coordinator, issue, world.members["faculty"].id), 409, "issue_closed")


def test_assigning_yourself_tells_nobody(world: World) -> None:
    issue = report(world.browser("student"))
    response = assign(world.browser("coordinator"), issue, world.members["coordinator"].id)
    assert response.status_code == 200, response.text
    assert told(world.browser("coordinator")) == []


# --- the assignee picker ---


def test_the_picker_lists_active_faculty_and_staff_by_name(world: World, session: Session) -> None:
    world.members["staff"].status = MembershipStatus.SUSPENDED
    session.commit()
    names = [a["name"] for a in world.browser("coordinator").get(ASSIGNEES).json()["items"]]
    assert sorted(names) == ["Admin", "Coordinator", "Dept Admin", "Faculty"]
    response = world.browser("admin").get(f"{ASSIGNEES}?query=fac")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item == {"id": str(world.members["faculty"].id), "name": "Faculty", "kind": "FACULTY"}
    assert "@" not in response.text  # names, never contact details


def test_the_picker_pages(world: World) -> None:
    coordinator = world.browser("coordinator")
    first = coordinator.get(f"{ASSIGNEES}?limit=3").json()
    second = coordinator.get(f"{ASSIGNEES}?limit=3&cursor={first['next_cursor']}").json()
    names = [a["name"] for a in first["items"] + second["items"]]
    assert sorted(names) == ["Admin", "Coordinator", "Dept Admin", "Faculty", "Staff"]
    assert second["next_cursor"] is None


def test_the_picker_is_for_coordinators_and_college_admins(world: World) -> None:
    for who in ("student", "faculty", "dept_admin"):
        response = world.browser(who).get(ASSIGNEES)
        assert response.status_code == 403, who
        assert "Faculty" not in response.text


# --- comments (ISSUE-005) ---


def test_who_comments_and_who_reads_what(world: World) -> None:
    student, coordinator = world.browser("student"), world.browser("coordinator")
    issue = report(student)
    assign(coordinator, issue, world.members["faculty"].id)
    response = comment(student, issue, "It also smells of smoke.")
    assert response.status_code == 201, response.text
    assert comment(coordinator, issue, INTERNAL, internal=True).status_code == 201
    assert comment(world.browser("faculty"), issue, "Electrician booked.").status_code == 201
    assert (
        comment(world.browser("faculty"), issue, "Part on order.", internal=True).status_code == 201
    )

    as_reporter = student.get(f"{ISSUES}/{issue['id']}")
    bodies = [u["body"] for u in as_reporter.json()["updates"] if u["kind"] == "COMMENT"]
    assert bodies == ["It also smells of smoke.", "Electrician booked."]
    assert INTERNAL not in as_reporter.text and "Part on order" not in as_reporter.text
    as_coordinator = coordinator.get(f"{ISSUES}/{issue['id']}").json()
    assert [u["is_internal"] for u in as_coordinator["updates"] if u["kind"] == "COMMENT"] == [
        False,
        True,
        False,
        True,
    ]
    assert as_coordinator["version"] == 2  # comments never cause a version conflict
    assert told(student) == []  # comments notify nobody (NOTIF-002)


def test_the_reporter_comments_publicly_and_not_once_rejected(world: World) -> None:
    student = world.browser("student")
    issue = report(student)
    refused(comment(student, issue, "Psst", internal=True), 403, "forbidden")
    moved(world.browser("coordinator"), issue, "REJECTED", note="Not ours.")
    refused(comment(student, issue, "But why?"), 403, "forbidden")


def test_strangers_cannot_comment(world: World) -> None:
    issue = report(world.browser("student"))
    for who in ("mech_student", "faculty", "dept_admin", "river_admin"):
        not_found(comment(world.browser(who), issue, "Hello"))
    for text in ("", "x" * 3001):
        assert comment(world.browser("student"), issue, text).status_code == 422


def test_notifications_carry_no_notes(world: World) -> None:  # NOTIF-004
    coordinator = world.browser("coordinator")
    moved(coordinator, report(world.browser("student")), "REJECTED", note=INTERNAL)
    response = world.browser("student").get(NOTIFICATIONS)
    assert INTERNAL not in response.text


def test_a_suspended_reporter_is_not_told(world: World, session: Session, conn: Connection) -> None:
    issue = report(world.browser("student"))
    world.members["student"].status = MembershipStatus.SUSPENDED
    session.commit()
    moved(world.browser("coordinator"), issue, "ACKNOWLEDGED")
    count = "SELECT count(*) FROM notifications WHERE subject_id = %s"
    assert conn.exec_driver_sql(count, (issue["id"],)).scalar() == 0


# --- what the issue page may offer ---


def actions_of(who: Browser, issue: dict[str, Any]) -> dict[str, Any]:
    response = who.get(f"{ISSUES}/{issue['id']}")
    assert response.status_code == 200, response.text
    actions: dict[str, Any] = response.json()["actions"]
    return actions


def test_each_viewer_is_offered_what_the_policies_allow(world: World, clock: Clock) -> None:
    coordinator = world.browser("coordinator")
    issue = report(world.browser("student"))
    assert actions_of(world.browser("student"), issue) == {
        "transitions": [],
        "assign": False,
        "comment": True,
        "comment_internal": False,
    }
    assert actions_of(coordinator, issue) == {
        "transitions": [
            {"to_status": "ACKNOWLEDGED", "needs_note": False},
            {"to_status": "REJECTED", "needs_note": True},
        ],
        "assign": True,
        "comment": True,
        "comment_internal": True,
    }
    issue = moved(coordinator, issue, "ACKNOWLEDGED")
    issue = assign(coordinator, issue, world.members["faculty"].id).json()
    as_assignee = actions_of(world.browser("faculty"), issue)
    assert as_assignee["transitions"] == [{"to_status": "IN_PROGRESS", "needs_note": False}]
    assert as_assignee["assign"] is False and as_assignee["comment_internal"] is True

    issue = moved(coordinator, issue, "IN_PROGRESS")
    issue = moved(coordinator, issue, "RESOLVED", note="Fixed.")
    reopen = [{"to_status": "ACKNOWLEDGED", "needs_note": True}]
    assert actions_of(world.browser("student"), issue)["transitions"] == reopen
    clock.advance(days=14)  # the reporter's window closes; sessions lapse too
    assert actions_of(world.browser("student"), issue)["transitions"] == []
    assert actions_of(world.browser("coordinator"), issue)["transitions"] == reopen


def test_a_rejected_issue_offers_the_reporter_nothing(world: World) -> None:
    issue = moved(
        world.browser("coordinator"), report(world.browser("student")), "REJECTED", note="No."
    )
    assert actions_of(world.browser("student"), issue) == {
        "transitions": [],
        "assign": False,
        "comment": False,
        "comment_internal": False,
    }
