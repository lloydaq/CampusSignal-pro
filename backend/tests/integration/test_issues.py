"""Campus issues, reporting and reading (ISSUE-001, 003, 006, 007, 009; US-08): who submits, the
submission limit, who reads which issue, the three lists, internal updates and duplicates.
Transitions, assignment and comments arrive in 5b; this file sets those states directly."""

import uuid
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from sqlalchemy import Connection, update
from sqlalchemy.orm import Session

from app.models import CampusIssue, IssueUpdate, IssueUpdateKind, MembershipKind, Role
from tests.integration.auth_helpers import error_of, scalar
from tests.integration.campus_world import CAMPUS, World, build_world
from tests.integration.conftest import Clock
from tests.integration.platform_helpers import Browser
from tests.integration.tenancy import add_member, make_user

pytestmark = pytest.mark.integration

ISSUES = f"{CAMPUS}/issues"
NO_SUCH_ISSUE = f"{ISSUES}/00000000-0000-4000-8000-000000000000"
SECRET = "Projector in room 204 sparks"  # a title only some people may see


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    world = build_world(session, app_factory())
    user = make_user(session, "coordinator@northfield.example", name="Coordinator")
    world.members["coordinator"] = add_member(
        session,
        user,
        world.north,
        MembershipKind.STAFF,
        department=None,
        roles=((Role.ISSUE_COORDINATOR, None),),
    )
    session.commit()
    return world


def body(**changes: Any) -> dict[str, Any]:
    return {
        "category": "CLASSROOM_EQUIPMENT",
        "title": SECRET,
        "description": "It sparks when switched on.",
        "location": "Main block, second floor",
        "room": "204",
        **changes,
    }


def report(who: Browser, **changes: Any) -> dict[str, Any]:
    response = who.post(ISSUES, body(**changes))
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def ids(response: httpx2.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [i["id"] for i in response.json()["items"]]


def not_found(response: httpx2.Response) -> None:
    assert response.status_code == 404, response.text
    assert error_of(response)["code"] == "not_found"
    assert SECRET not in response.text


def set_issue(session: Session, issue_id: str, **values: Any) -> None:
    session.execute(
        update(CampusIssue).where(CampusIssue.id == uuid.UUID(issue_id)).values(**values)
    )
    session.commit()


# --- submitting (ISSUE-001, US-08) ---


def test_a_member_reports_an_issue(world: World, conn: Connection, clock: Clock) -> None:
    issue = report(world.browser("student"))
    assert issue["status"] == "SUBMITTED"
    assert issue["title"] == SECRET and issue["room"] == "204"
    assert issue["reporter_name"] == "Student" and issue["assignee_name"] is None
    assert issue["created_at"].startswith("2026-10-21T12:00:00")
    assert [(u["kind"], u["actor_name"]) for u in issue["updates"]] == [("CREATED", "Student")]
    action, metadata = conn.exec_driver_sql(
        "SELECT action, metadata::text FROM audit_log WHERE target_id = %s", (issue["id"],)
    ).one()
    assert action == "issue.created"
    assert SECRET not in metadata and "sparks" not in metadata  # no report text in the audit log


def test_every_kind_of_member_can_report(world: World) -> None:
    for who in ("admin", "dept_admin", "faculty", "coordinator", "mech_student"):
        assert world.browser(who).post(ISSUES, body()).status_code == 201, who


@pytest.mark.parametrize(
    "change",
    [
        {"title": "x" * 121},
        {"title": "   "},
        {"description": "x" * 3001},
        {"location": ""},
        {"room": "x" * 101},
        {"category": "PARKING"},
        {"title": "bad\x07title"},
    ],
)
def test_invalid_reports_are_refused(world: World, change: dict[str, Any]) -> None:
    response = world.browser("student").post(ISSUES, body(**change))
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "extra",
    [
        {"college_id": "00000000-0000-4000-8000-000000000000"},
        {"status": "RESOLVED"},
        {"reporter_membership_id": "00000000-0000-4000-8000-000000000000"},
        {"assignee_membership_id": "00000000-0000-4000-8000-000000000000"},
    ],
)
def test_clients_cannot_set_what_the_server_decides(world: World, extra: dict[str, Any]) -> None:
    assert world.browser("student").post(ISSUES, body(**extra)).status_code == 422


def test_the_room_is_optional(world: World) -> None:
    payload = body()
    del payload["room"]
    assert world.browser("student").post(ISSUES, payload).json()["room"] is None


def test_five_reports_a_day_then_429(world: World, clock: Clock) -> None:  # ISSUE-007, US-08
    student = world.browser("student")
    for _ in range(5):
        report(student)
        clock.advance(hours=1)
    refused = student.post(ISSUES, body())
    assert refused.status_code == 429
    assert error_of(refused)["code"] == "rate_limited"
    # The first report leaves the 24-hour window 19 hours from now.
    assert refused.headers["Retry-After"] == str(19 * 3600)
    assert scalar_count(world, student) == 5
    report(world.browser("mech_student"))  # the limit is per member
    clock.advance(hours=19)
    report(student)


def scalar_count(world: World, who: Browser) -> int:
    return len(ids(who.get(f"{ISSUES}?scope=mine")))


# --- reading one issue (ISSUE-003, US-08) ---


def test_who_reads_an_issue(world: World, session: Session) -> None:
    issue = report(world.browser("student"))
    path = f"{ISSUES}/{issue['id']}"
    for who in ("student", "coordinator", "admin"):
        response = world.browser(who).get(path)
        assert response.status_code == 200, who
        assert response.json()["title"] == SECRET
    # Another student (US-08), faculty, a department admin, another college: not even there.
    for who in ("mech_student", "faculty", "dept_admin", "river_admin", "river_student"):
        not_found(world.browser(who).get(path))
    not_found(world.browser("student").get(NO_SUCH_ISSUE))

    # The current assignee reads it; once reassigned, they no longer do.
    set_issue(session, issue["id"], assignee_membership_id=world.members["faculty"].id)
    assert world.browser("faculty").get(path).json()["assignee_name"] == "Faculty"
    set_issue(session, issue["id"], assignee_membership_id=world.members["dept_admin"].id)
    not_found(world.browser("faculty").get(path))


def test_internal_updates_never_reach_the_reporter(world: World, session: Session) -> None:
    issue = report(world.browser("student"))
    for internal, text in ((True, "Vendor quote is 40k, wait"), (False, "Electrician booked")):
        session.add(
            IssueUpdate(
                college_id=world.north.id,
                issue_id=uuid.UUID(issue["id"]),
                actor_membership_id=world.members["coordinator"].id,
                kind=IssueUpdateKind.COMMENT,
                body=text,
                is_internal=internal,
            )
        )
    session.commit()
    path = f"{ISSUES}/{issue['id']}"
    as_reporter = world.browser("student").get(path)
    assert [u["body"] for u in as_reporter.json()["updates"]] == [None, "Electrician booked"]
    assert "Vendor quote" not in as_reporter.text
    as_coordinator = world.browser("coordinator").get(path).json()["updates"]
    assert [u["is_internal"] for u in as_coordinator] == [False, True, False]


def test_a_duplicate_shows_only_the_originals_status(
    world: World, session: Session, clock: Clock
) -> None:
    original = report(world.browser("mech_student"), title="Original secret title")
    set_issue(session, original["id"], status="RESOLVED", resolved_at=clock.now)
    copy = report(world.browser("student"))
    set_issue(session, copy["id"], status="REJECTED", duplicate_of_id=uuid.UUID(original["id"]))

    as_reporter = world.browser("student").get(f"{ISSUES}/{copy['id']}")
    duplicate_of = as_reporter.json()["duplicate_of"]
    assert duplicate_of["id"] is None
    assert duplicate_of["status"] == "RESOLVED" and duplicate_of["resolved_at"] is not None
    for leak in ("Original secret title", "Mech Student", original["id"]):
        assert leak not in as_reporter.text, leak
    as_coordinator = world.browser("coordinator").get(f"{ISSUES}/{copy['id']}").json()
    assert as_coordinator["duplicate_of"]["id"] == original["id"]


# --- lists (ISSUE-003, 004, 009) ---


def test_mine_lists_only_my_reports(world: World) -> None:
    mine = report(world.browser("student"))
    report(world.browser("mech_student"))
    report(world.browser("river_student"))
    assert ids(world.browser("student").get(f"{ISSUES}?scope=mine")) == [mine["id"]]


def test_assigned_lists_only_issues_assigned_to_me(world: World, session: Session) -> None:
    first = report(world.browser("student"))
    report(world.browser("mech_student"))
    set_issue(session, first["id"], assignee_membership_id=world.members["faculty"].id)
    assert ids(world.browser("faculty").get(f"{ISSUES}?scope=assigned")) == [first["id"]]
    assert ids(world.browser("dept_admin").get(f"{ISSUES}?scope=assigned")) == []


def test_the_queue_is_for_coordinators_and_college_admins(world: World) -> None:
    report(world.browser("student"))
    for who in ("student", "faculty", "dept_admin"):
        response = world.browser(who).get(f"{ISSUES}?scope=queue")
        assert response.status_code == 403, who
        assert SECRET not in response.text
    for who in ("coordinator", "admin"):
        assert len(ids(world.browser(who).get(f"{ISSUES}?scope=queue"))) == 1, who


def test_the_queue_puts_the_oldest_unacknowledged_first(
    world: World, session: Session, clock: Clock
) -> None:
    student = world.browser("student")
    older_acknowledged = report(student, title="A")
    clock.advance(hours=1)
    old_new = report(student, title="B")
    clock.advance(hours=1)
    newest_new = report(world.browser("mech_student"), title="C")
    set_issue(session, older_acknowledged["id"], status="ACKNOWLEDGED")
    queue = ids(world.browser("coordinator").get(f"{ISSUES}?scope=queue"))
    assert queue == [old_new["id"], newest_new["id"], older_acknowledged["id"]]
    # Pages follow the same order without gaps or repeats.
    coordinator = world.browser("coordinator")
    first = coordinator.get(f"{ISSUES}?scope=queue&limit=2").json()
    second = coordinator.get(f"{ISSUES}?scope=queue&limit=2&cursor={first['next_cursor']}").json()
    assert [i["id"] for i in first["items"] + second["items"]] == queue
    assert second["next_cursor"] is None


def test_the_queue_filters(world: World, session: Session, clock: Clock) -> None:
    student = world.browser("student")
    wifi = report(student, category="NETWORK")
    clock.advance(days=3)
    lab = report(student, category="LABORATORY")
    set_issue(
        session,
        lab["id"],
        status="ACKNOWLEDGED",
        assignee_membership_id=world.members["faculty"].id,
    )
    coordinator = world.browser("coordinator")
    assert ids(coordinator.get(f"{ISSUES}?scope=queue&category=NETWORK")) == [wifi["id"]]
    assert ids(coordinator.get(f"{ISSUES}?scope=queue&status=ACKNOWLEDGED")) == [lab["id"]]
    faculty = world.members["faculty"].id
    assert ids(coordinator.get(f"{ISSUES}?scope=queue&assignee_id={faculty}")) == [lab["id"]]
    assert ids(coordinator.get(f"{ISSUES}?scope=queue&older_than_days=2")) == [wifi["id"]]


def test_list_defaults_and_bad_parameters(world: World) -> None:
    mine = report(world.browser("student"))
    assert ids(world.browser("student").get(ISSUES)) == [mine["id"]]  # scope defaults to mine
    for query in ("scope=everything", "status=DONE", "cursor=not-a-cursor", "older_than_days=-1"):
        assert world.browser("coordinator").get(f"{ISSUES}?{query}").status_code == 422, query


def test_timeline_rows_are_append_only(world: World, conn: Connection) -> None:
    issue = report(world.browser("student"))
    with pytest.raises(Exception, match="append-only"), conn.begin_nested():
        conn.exec_driver_sql(
            "UPDATE issue_updates SET body = 'rewritten' WHERE issue_id = %s", (issue["id"],)
        )
    with pytest.raises(Exception, match="append-only"), conn.begin_nested():
        conn.exec_driver_sql("DELETE FROM issue_updates WHERE issue_id = %s", (issue["id"],))
    count = "SELECT count(*) FROM issue_updates WHERE issue_id = :id"
    assert scalar(conn, count, id=issue["id"]) == 1
