"""In-app notifications (NOTIF-001…005, NOTICE-007; US-12): who is told about a notice, what
people can read of their own, and what a decision on a join request sends."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from sqlalchemy import Connection, func, select
from sqlalchemy.orm import Session

from app.models import MembershipKind, Notification, Role
from app.services import notifications as notification_service
from tests.integration.auth_helpers import PREFIX, error_of, scalar
from tests.integration.campus_world import CAMPUS, World, build_world
from tests.integration.conftest import Clock
from tests.integration.platform_helpers import Browser
from tests.integration.tenancy import add_member, make_user, roster_entry

pytestmark = pytest.mark.integration

NOTICES = f"{CAMPUS}/notices"
MINE = f"{PREFIX}/me/notifications"
NORTH_MEMBERS = ("admin", "dept_admin", "faculty", "student", "mech_student", "mech_admin")
CSE_MEMBERS = ("admin", "dept_admin", "faculty", "student")


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    world = build_world(session, app_factory())
    user = make_user(session, "mech_admin@northfield.example", name="Mech Admin")
    world.members["mech_admin"] = add_member(
        session,
        user,
        world.north,
        MembershipKind.FACULTY,
        department="MECH",
        roles=((Role.DEPARTMENT_ADMIN, "MECH"),),
    )
    session.commit()
    return world


def publish(who: Browser, **changes: Any) -> dict[str, Any]:
    payload = {
        "title": "Campus closed tomorrow",
        "body": "Heavy rain.",
        "category": "GENERAL",
        "scope": "COLLEGE",
        "priority": "URGENT",
        "publish": True,
        **changes,
    }
    response = who.post(NOTICES, payload)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def unread(who: Browser) -> int:
    response = who.get(f"{MINE}/unread-count")
    assert response.status_code == 200, response.text
    return int(response.json()["unread"])


def titles(who: Browser, **params: Any) -> list[str]:
    response = who.get(MINE, **params)
    assert response.status_code == 200, response.text
    return [n["title"] for n in response.json()["items"]]


def dept(world: World, code: str) -> str:
    return str(world.north.departments[code].id)


# --- who is told about a notice ------------------------------------------------------------------


def test_an_urgent_college_notice_tells_every_member_of_that_college_once(world: World) -> None:
    published = publish(world.browser("admin"))

    for who in NORTH_MEMBERS:
        reader = world.browser(who)
        assert unread(reader) == 1, who
        assert titles(reader) == ["Urgent notice: Campus closed tomorrow"], who
        item = reader.get(MINE).json()["items"][0]
        assert (item["type"], item["subject_type"], item["subject_id"], item["read"]) == (
            "NOTICE_PUBLISHED",
            "NOTICE",
            published["id"],
            False,
        )
    for outsider in ("river_admin", "river_student"):
        assert unread(world.browser(outsider)) == 0
        assert titles(world.browser(outsider)) == []


def test_an_urgent_department_notice_tells_only_that_departments_members(world: World) -> None:
    publish(world.browser("dept_admin"), scope="DEPARTMENT", department_id=dept(world, "CSE"))

    for who in CSE_MEMBERS:
        assert unread(world.browser(who)) == 1, who
    for who in ("mech_student", "mech_admin", "river_student"):
        assert unread(world.browser(who)) == 0, who


def test_a_high_notice_is_labelled_important(world: World) -> None:
    publish(world.browser("admin"), priority="HIGH", title="Fee deadline")
    assert titles(world.browser("student")) == ["Important notice: Fee deadline"]


def test_a_normal_notice_tells_nobody(world: World) -> None:
    publish(world.browser("admin"), priority="NORMAL")
    assert all(unread(world.browser(who)) == 0 for who in NORTH_MEMBERS)


def test_a_draft_tells_nobody_until_it_is_published(world: World) -> None:
    admin = world.browser("admin")
    draft = publish(admin, publish=False)
    assert unread(world.browser("student")) == 0
    admin.post(f"{NOTICES}/{draft['id']}/publish", {"version": draft["version"]})
    assert unread(world.browser("student")) == 1


def test_editing_a_published_notice_tells_nobody_again(world: World) -> None:
    admin = world.browser("admin")
    published = publish(admin, priority="NORMAL")
    version = published["version"]
    for change in ({"priority": "URGENT"}, {"title": "Revised"}, {"priority": "HIGH"}):
        response = admin.patch(f"{NOTICES}/{published['id']}", {"version": version, **change})
        assert response.status_code == 200
        version += 1
    assert unread(world.browser("student")) == 0
    urgent = publish(admin, title="Second")
    admin.patch(f"{NOTICES}/{urgent['id']}", {"version": 2, "title": "Second, revised"})
    assert titles(world.browser("student")) == ["Urgent notice: Second"]


def test_people_who_are_not_active_members_are_not_told(world: World) -> None:
    admin = world.browser("admin")
    suspended = world.members["student"]
    response = admin.patch(
        f"{CAMPUS}/members/{suspended.id}", {"status": "SUSPENDED", "reason": "Fees unpaid"}
    )
    assert response.status_code == 200
    publish(admin)
    # Reactivating later doesn't hand them what they missed.
    assert admin.patch(f"{CAMPUS}/members/{suspended.id}", {"status": "ACTIVE"}).status_code == 200
    assert unread(world.browser("student")) == 0
    assert unread(world.browser("faculty")) == 1


def test_a_failed_publish_leaves_no_notifications(world: World, clock: Clock) -> None:
    admin = world.browser("admin")
    draft = publish(admin, publish=False, expires_at=(clock.now + timedelta(hours=1)).isoformat())
    clock.advance(hours=2)
    refused = admin.post(f"{NOTICES}/{draft['id']}/publish", {"version": 1})
    assert refused.status_code == 422
    assert all(unread(world.browser(who)) == 0 for who in NORTH_MEMBERS)


def test_withdrawing_a_notice_takes_its_notifications_away(world: World) -> None:
    admin = world.browser("admin")
    published = publish(admin, title="Wrongly sent")
    other = publish(admin, title="Still true")
    assert unread(world.browser("student")) == 2

    assert (
        admin.post(f"{NOTICES}/{published['id']}/withdraw", {"reason": "oops"}).status_code == 200
    )

    student = world.browser("student")
    assert titles(student) == ["Urgent notice: Still true"]
    assert unread(student) == 1
    assert other["id"]


def test_telling_people_twice_about_one_notice_is_a_no_op(
    world: World, session: Session, clock: Clock
) -> None:
    from app.models import Notice

    published = publish(world.browser("admin"))
    notice = session.get(Notice, published["id"])
    assert notice is not None
    before = scalar_count(session)
    assert notification_service.notify_notice_published(session, notice, clock.now) == 0
    assert scalar_count(session) == before


def scalar_count(session: Session) -> int:
    return int(session.execute(select(func.count()).select_from(Notification)).scalar_one())


# --- reading -------------------------------------------------------------------------------------


def test_the_list_is_newest_first_and_pages_with_a_cursor(world: World, clock: Clock) -> None:
    admin = world.browser("admin")
    for n in range(5):
        clock.advance(minutes=1)
        publish(admin, title=f"Notice {n}")
    student = world.browser("student")

    first = student.get(MINE, limit=2).json()
    assert [n["title"] for n in first["items"]] == [
        "Urgent notice: Notice 4",
        "Urgent notice: Notice 3",
    ]
    seen = [n["title"] for n in first["items"]]
    cursor = first["next_cursor"]
    while cursor:
        page = student.get(MINE, limit=2, cursor=cursor).json()
        seen += [n["title"] for n in page["items"]]
        cursor = page["next_cursor"]
    assert seen == [f"Urgent notice: Notice {n}" for n in (4, 3, 2, 1, 0)]
    assert student.get(MINE, cursor="garbage").status_code == 422


def test_marking_one_read_lowers_the_count_and_is_repeatable(world: World, clock: Clock) -> None:
    admin = world.browser("admin")
    publish(admin, title="One")
    clock.advance(minutes=1)
    publish(admin, title="Two")
    student = world.browser("student")
    newest = student.get(MINE).json()["items"][0]

    marked = student.post(f"{MINE}/{newest['id']}/read")
    assert marked.status_code == 200 and marked.json()["read"] is True
    assert unread(student) == 1
    assert student.post(f"{MINE}/{newest['id']}/read").status_code == 200  # idempotent
    assert unread(student) == 1
    assert titles(student, unread="true") == ["Urgent notice: One"]
    assert len(titles(student)) == 2  # read ones stay in the list


def test_mark_all_read_clears_the_count(world: World) -> None:
    publish(world.browser("admin"), title="One")
    publish(world.browser("admin"), title="Two")
    student = world.browser("student")
    assert unread(student) == 2
    assert student.post(f"{MINE}/read-all").json() == {"marked": 2}
    assert unread(student) == 0
    assert student.post(f"{MINE}/read-all").json() == {"marked": 0}
    assert unread(world.browser("faculty")) == 2  # nobody else's changed


def test_nobody_can_touch_someone_elses_notification(world: World) -> None:
    publish(world.browser("admin"))
    mine = world.browser("student").get(MINE).json()["items"][0]["id"]

    for intruder in ("faculty", "river_student", "river_admin"):
        refused = world.browser(intruder).post(f"{MINE}/{mine}/read")
        assert refused.status_code == 404, intruder
        assert error_of(refused)["code"] == "not_found"
        assert "Campus closed" not in refused.text
    unknown = world.browser("student").post(f"{MINE}/00000000-0000-4000-8000-000000000000/read")
    assert unknown.status_code == 404
    assert unread(world.browser("student")) == 1  # still unread


def test_a_suspended_member_sees_no_college_notifications_until_reinstated(world: World) -> None:
    admin = world.browser("admin")
    publish(admin)
    student = world.browser("student")
    mine = student.get(MINE).json()["items"][0]["id"]
    member = world.members["student"]
    admin.patch(f"{CAMPUS}/members/{member.id}", {"status": "SUSPENDED", "reason": "Review"})

    assert titles(student) == [] and unread(student) == 0
    assert student.post(f"{MINE}/{mine}/read").status_code == 404
    assert student.post(f"{MINE}/read-all").json() == {"marked": 0}

    admin.patch(f"{CAMPUS}/members/{member.id}", {"status": "ACTIVE"})
    assert unread(student) == 1  # the earlier notification was never marked read


def test_after_moving_colleges_the_old_colleges_notifications_are_gone_from_view(
    world: World, session: Session
) -> None:
    """NOTIF-001: only the current ACTIVE membership's college counts."""
    publish(world.browser("admin"), title="Northfield only")
    student = world.browser("student")
    old = student.get(MINE).json()["items"][0]["id"]
    member = world.members["student"]
    ended = world.browser("admin").patch(
        f"{CAMPUS}/members/{member.id}", {"status": "ENDED", "reason": "Transferred"}
    )
    assert ended.status_code == 200
    user = member.user_id
    from app.models import User

    add_member(
        session,
        session.get(User, user),  # type: ignore[arg-type]
        world.river,
        MembershipKind.STUDENT,
        department="CSE",
    )
    session.commit()
    publish(world.browser("river_admin"), title="Riverside news")

    moved = Browser(world.app, "student@northfield.example")
    assert titles(moved) == ["Urgent notice: Riverside news"]
    assert unread(moved) == 1
    assert moved.post(f"{MINE}/{old}/read").status_code == 404


def test_every_fan_out_is_audited_with_its_size(world: World, conn: Connection) -> None:
    publish(world.browser("admin"))
    assert (
        scalar(
            conn,
            "SELECT count(*) FROM audit_log WHERE action = 'notice.notified' "
            "AND (metadata ->> 'notified')::int = 6 AND college_id = :c",
            c=world.north.id,
        )
        == 1
    )


def test_notifications_need_a_signed_in_user(world: World) -> None:
    anonymous = Browser(world.app)
    assert anonymous.get(MINE).status_code == 401
    assert anonymous.get(f"{MINE}/unread-count").status_code == 401


# --- decisions on join requests ----------------------------------------------------------------


def _apply(world: World, session: Session, roll: str, email: str) -> Browser:
    make_user(session, email, name="Applicant")
    session.commit()
    applicant = Browser(world.app, email)
    response = applicant.post(
        f"{PREFIX}/me/membership-requests", {"college_slug": "northfield", "roll_number": roll}
    )
    assert response.status_code == 202, response.text
    return applicant


def _request_id(world: World) -> str:
    items = world.browser("admin").get(f"{CAMPUS}/membership-requests").json()["items"]
    assert len(items) == 1
    return str(items[0]["id"])


def test_approving_a_request_tells_the_new_member(world: World, session: Session) -> None:
    roster_entry(session, world.north, "N-301", department="CSE", email=None)
    session.commit()
    applicant = _apply(world, session, "N-301", "newbie@northfield.example")
    assert unread(applicant) == 0

    admin = world.browser("admin")
    assert (
        admin.post(f"{CAMPUS}/membership-requests/{_request_id(world)}/approve").status_code == 200
    )

    assert titles(applicant) == ["You've joined Northfield Institute"]
    assert unread(applicant) == 1
    item = applicant.get(MINE).json()["items"][0]
    assert item["type"] == "MEMBERSHIP_DECIDED" and item["subject_type"] == "MEMBERSHIP"
    assert unread(world.browser("faculty")) == 0  # nobody else is told


def test_rejecting_a_request_tells_the_applicant_without_the_reason(
    world: World, session: Session, conn: Connection
) -> None:
    applicant = _apply(world, session, "N-404", "ghost@northfield.example")
    admin = world.browser("admin")
    rejected = admin.post(
        f"{CAMPUS}/membership-requests/{_request_id(world)}/reject",
        {"reason": "Not enrolled here"},
    )
    assert rejected.status_code == 200

    # The applicant isn't a member, yet still sees it: it follows the person (college_id NULL).
    assert titles(applicant) == ["Your request to join Northfield Institute wasn't approved"]
    assert "Not enrolled" not in applicant.get(MINE).text
    assert (
        scalar(
            conn,
            "SELECT count(*) FROM notifications WHERE title LIKE 'Your request%%' "
            "AND college_id IS NULL",
        )
        == 1
    )


# --- what a notification may contain (NOTIF-004) ----------------------------------------------


def test_notifications_hold_references_and_titles_only(world: World, conn: Connection) -> None:
    publish(world.browser("admin"))
    rows = conn.exec_driver_sql(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'notifications'"
    ).all()
    assert {r[0] for r in rows} == {
        "id",
        "user_id",
        "college_id",
        "type",
        "subject_type",
        "subject_id",
        "title",
        "read_at",
        "created_at",
    }
    body: httpx2.Response = world.browser("student").get(MINE)
    assert set(body.json()["items"][0]) == {
        "id",
        "type",
        "title",
        "subject_type",
        "subject_id",
        "read",
        "created_at",
    }
