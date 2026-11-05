"""Community posts, comments and reactions (COMMUNITY-001…005, 008, 009; US-10 first half):
who posts where, who reads which feed and post, editing and soft deletion, comments,
"Helpful" reactions, the hourly limits, and a fixed number of queries per feed page.
Moderation (reports, hiding) is in test_moderation.py; hidden posts are set directly here."""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from sqlalchemy import Connection, event, update
from sqlalchemy.orm import Session

from app.models import MembershipKind, Post
from tests.integration.auth_helpers import error_of, scalar
from tests.integration.campus_world import CAMPUS, World, build_world
from tests.integration.conftest import Clock
from tests.integration.platform_helpers import Browser
from tests.integration.tenancy import add_member, make_user

pytestmark = pytest.mark.integration

POSTS = f"{CAMPUS}/posts"
SECRET = "CSE lab keys are with the guard"  # a department-only sentence


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    world = build_world(session, app_factory())
    user = make_user(session, "staff@northfield.example", name="Staff")
    world.members["staff"] = add_member(
        session, user, world.north, MembershipKind.STAFF, department=None
    )
    session.commit()
    return world


def post(
    who: Browser, body: str = "Anyone for chess?", visibility: str = "COLLEGE"
) -> dict[str, Any]:
    response = who.post(POSTS, {"body": body, "visibility": visibility})
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def feed(who: Browser, query: str = "") -> list[str]:
    response = who.get(f"{POSTS}?{query}")
    assert response.status_code == 200, response.text
    return [p["body"] for p in response.json()["items"]]


def not_found(response: httpx2.Response) -> None:
    assert response.status_code == 404, response.text
    assert error_of(response)["code"] == "not_found"
    assert SECRET not in response.text


def set_post(session: Session, post_id: str, **values: Any) -> None:
    if values.get("status") == "HIDDEN":  # a hidden post always says why (migration 0011)
        values = {
            "hidden_reason": "Off-topic",
            "hidden_at": datetime(2026, 10, 21, tzinfo=UTC),
            **values,
        }
    session.execute(update(Post).where(Post.id == uuid.UUID(post_id)).values(**values))
    session.commit()


# --- posting (COMMUNITY-001, 009, 010) ---


def test_a_member_posts_to_the_college(world: World, clock: Clock) -> None:
    created = post(world.browser("student"))
    assert created["visibility"] == "COLLEGE" and created["department"] is None
    assert created["author"] == {"name": "Student", "kind": "STUDENT"}  # never anonymous
    assert created["created_at"].startswith("2026-10-21T12:00:00")
    assert created["reaction_count"] == 0 and created["comment_count"] == 0
    assert created["can_edit"] and created["can_delete"] and created["can_engage"]
    for who in ("mech_student", "faculty", "staff", "admin"):
        assert feed(world.browser(who)) == ["Anyone for chess?"], who
    assert feed(world.browser("river_student")) == []
    not_found(world.browser("river_admin").get(f"{POSTS}/{created['id']}"))


def test_faculty_and_staff_carry_their_kind(world: World) -> None:  # COMMUNITY-009
    assert post(world.browser("faculty"))["author"]["kind"] == "FACULTY"
    assert post(world.browser("staff"))["author"]["kind"] == "STAFF"


def test_a_department_post_goes_to_the_posters_own_department(world: World) -> None:
    created = post(world.browser("student"), SECRET, "DEPARTMENT")
    assert created["department"]["code"] == "CSE"
    # Not even a department admin of another department can aim it elsewhere: there's no field.
    response = world.browser("student").post(
        POSTS,
        {
            "body": "x",
            "visibility": "DEPARTMENT",
            "department_id": str(world.north.departments["MECH"].id),
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "extra",
    [
        {"college_id": "00000000-0000-4000-8000-000000000000"},
        {"author_membership_id": "00000000-0000-4000-8000-000000000000"},
        {"status": "HIDDEN"},
        {"anonymous": True},
    ],
)
def test_clients_cannot_set_what_the_server_decides(world: World, extra: dict[str, Any]) -> None:
    response = world.browser("student").post(POSTS, {"body": "x", "visibility": "COLLEGE", **extra})
    assert response.status_code == 422


@pytest.mark.parametrize("body", ["", "   ", "x" * 5001, "bell\x07"])
def test_invalid_posts_are_refused(world: World, body: str) -> None:
    response = world.browser("student").post(POSTS, {"body": body, "visibility": "COLLEGE"})
    assert response.status_code == 422, body


def test_text_is_kept_as_written(world: World) -> None:
    body = "Line one\n\n<b>not bold</b> https://northfield.example/clubs"
    assert post(world.browser("student"), body)["body"] == body  # escaping is the page's job


def test_without_a_department_only_college_posts(world: World) -> None:
    response = world.browser("staff").post(POSTS, {"body": "x", "visibility": "DEPARTMENT"})
    assert response.status_code == 422
    assert error_of(response)["details"][0]["field"] == "visibility"


# --- reading (COMMUNITY-002, US-10) ---


def test_department_posts_stay_in_their_department(world: World) -> None:  # US-10
    created = post(world.browser("student"), SECRET, "DEPARTMENT")
    path = f"{POSTS}/{created['id']}"
    cse = world.north.departments["CSE"].id
    for who in ("student", "faculty", "dept_admin", "admin"):
        assert world.browser(who).get(path).status_code == 200, who
        assert feed(world.browser(who), f"feed=department&department_id={cse}") == [SECRET], who
    # The CSE members' own department feed, no id needed.
    assert feed(world.browser("faculty"), "feed=department") == [SECRET]
    for who in ("mech_student", "staff", "river_admin", "river_student"):
        not_found(world.browser(who).get(path))
        not_found(world.browser(who).get(f"{POSTS}?feed=department&department_id={cse}"))
    assert feed(world.browser("mech_student"), "feed=department") == []
    for who in ("student", "mech_student", "admin"):
        assert SECRET not in feed(world.browser(who)), who  # the college feed


def test_department_feed_needs_a_department(world: World) -> None:
    not_found(world.browser("staff").get(f"{POSTS}?feed=department"))
    unknown = f"{POSTS}?feed=department&department_id={uuid.uuid4()}"
    not_found(world.browser("admin").get(unknown))
    river = world.river.departments["CSE"].id
    not_found(world.browser("admin").get(f"{POSTS}?feed=department&department_id={river}"))
    assert world.browser("student").get(f"{POSTS}?feed=everything").status_code == 422


def test_the_feed_is_newest_first_in_pages_of_20(world: World, clock: Clock) -> None:
    for n in range(23):
        post(world.browser("faculty" if n % 2 else "admin"), f"Post {n}")
        clock.advance(minutes=1)  # the limit is per member per hour: two posters, 23 minutes
        if n % 10 == 9:
            clock.advance(hours=1)
    student = world.browser("student")
    first = student.get(POSTS).json()
    assert [p["body"] for p in first["items"]][:2] == ["Post 22", "Post 21"]
    assert len(first["items"]) == 20
    second = student.get(f"{POSTS}?cursor={first['next_cursor']}").json()
    assert [p["body"] for p in second["items"]] == ["Post 2", "Post 1", "Post 0"]
    assert second["next_cursor"] is None


def test_hidden_posts_leave_the_feed_except_for_moderators(world: World, session: Session) -> None:
    college = post(world.browser("student"), "College rumour")
    department = post(world.browser("student"), SECRET, "DEPARTMENT")
    for p in (college, department):
        set_post(session, p["id"], status="HIDDEN")
    cse = world.north.departments["CSE"].id
    assert feed(world.browser("faculty")) == []
    assert feed(world.browser("faculty"), "feed=department") == []
    not_found(world.browser("faculty").get(f"{POSTS}/{college['id']}"))
    assert feed(world.browser("admin")) == ["College rumour"]
    assert feed(world.browser("dept_admin"), f"feed=department&department_id={cse}") == [SECRET]
    assert feed(world.browser("dept_admin")) == []  # a college post isn't theirs to moderate
    # The author still opens their own, frozen.
    mine = world.browser("student").get(f"{POSTS}/{college['id']}").json()
    assert mine["status"] == "HIDDEN" and not mine["can_engage"] and not mine["can_edit"]
    assert mine["can_delete"]


# --- editing and deleting (COMMUNITY-005) ---


def test_the_author_edits_and_it_shows(world: World, clock: Clock) -> None:
    created = post(world.browser("student"))
    path = f"{POSTS}/{created['id']}"
    clock.advance(minutes=5)
    unchanged = world.browser("student").patch(path, {"body": "Anyone for chess?"}).json()
    assert unchanged["edited_at"] is None  # saving the same words isn't an edit
    edited = world.browser("student").patch(path, {"body": "Chess at 5, library"}).json()
    assert edited["body"] == "Chess at 5, library"
    assert edited["edited_at"].startswith("2026-10-21T12:05:00")
    for who in ("faculty", "admin"):
        response = world.browser(who).patch(path, {"body": "Hacked"})
        assert response.status_code == 403, who
        assert world.browser(who).get(path).json()["can_edit"] is False
    not_found(world.browser("river_admin").patch(path, {"body": "Hacked"}))


def test_deleting_removes_the_post_from_every_read(world: World, conn: Connection) -> None:
    created = post(world.browser("student"), SECRET, "DEPARTMENT")
    path = f"{POSTS}/{created['id']}"
    assert world.browser("faculty").send("DELETE", path).status_code == 403
    assert world.browser("admin").send("DELETE", path).status_code == 403  # moderators hide instead
    assert world.browser("student").send("DELETE", path).status_code == 204
    for who in ("student", "admin", "dept_admin"):
        not_found(world.browser(who).get(path))
        assert SECRET not in feed(world.browser(who), "feed=department")
    not_found(world.browser("student").send("DELETE", path))
    # Soft: the row stays (reports may point at it), only marked deleted.
    deleted = scalar(
        conn, "SELECT deleted_at IS NOT NULL FROM posts WHERE id = :id", id=created["id"]
    )
    assert deleted is True


# --- comments (COMMUNITY-003, 005) ---


def test_comments_in_order_and_counted(world: World, clock: Clock) -> None:
    created = post(world.browser("student"))
    comments = f"{POSTS}/{created['id']}/comments"
    for who, text in (
        ("faculty", "I'm in"),
        ("mech_student", "Me too"),
        ("admin", "Board in room 2"),
    ):
        response = world.browser(who).post(comments, {"body": text})
        assert response.status_code == 201, response.text
        clock.advance(minutes=1)
    listed = world.browser("student").get(comments).json()
    assert [(c["author"]["name"], c["body"]) for c in listed["items"]] == [
        ("Faculty", "I'm in"),
        ("Mech Student", "Me too"),
        ("Admin", "Board in room 2"),
    ]
    assert world.browser("student").get(f"{POSTS}/{created['id']}").json()["comment_count"] == 3
    first = world.browser("student").get(f"{comments}?limit=2").json()
    rest = world.browser("student").get(f"{comments}?limit=2&cursor={first['next_cursor']}").json()
    assert [c["body"] for c in first["items"] + rest["items"]] == [
        "I'm in",
        "Me too",
        "Board in room 2",
    ]
    assert world.browser("student").post(comments, {"body": "x" * 2001}).status_code == 422


def test_comments_follow_the_post(world: World) -> None:
    created = post(world.browser("student"), SECRET, "DEPARTMENT")
    comments = f"{POSTS}/{created['id']}/comments"
    assert world.browser("faculty").post(comments, {"body": "Thanks"}).status_code == 201
    for who in ("mech_student", "river_admin"):
        not_found(world.browser(who).get(comments))
        not_found(world.browser(who).post(comments, {"body": "Let me in"}))


def test_only_the_author_edits_or_deletes_a_comment(world: World, clock: Clock) -> None:
    created = post(world.browser("student"))
    added = (
        world.browser("faculty").post(f"{POSTS}/{created['id']}/comments", {"body": "Yes"}).json()
    )
    path = f"{CAMPUS}/comments/{added['id']}"
    assert added["can_edit"] and added["can_delete"]
    for who in ("student", "admin"):  # the post's author and a moderator alike
        assert world.browser(who).patch(path, {"body": "No"}).status_code == 403, who
        assert world.browser(who).send("DELETE", path).status_code == 403, who
    clock.advance(minutes=1)
    edited = world.browser("faculty").patch(path, {"body": "Yes, at 5"}).json()
    assert edited["body"] == "Yes, at 5" and edited["edited_at"] is not None
    assert world.browser("faculty").send("DELETE", path).status_code == 204
    assert world.browser("student").get(f"{POSTS}/{created['id']}/comments").json()["items"] == []
    assert world.browser("student").get(f"{POSTS}/{created['id']}").json()["comment_count"] == 0
    not_found(world.browser("faculty").patch(path, {"body": "Back"}))
    not_found(world.browser("river_admin").send("DELETE", path))


def test_a_hidden_post_takes_no_comments_or_reactions(world: World, session: Session) -> None:
    created = post(world.browser("student"))
    set_post(session, created["id"], status="HIDDEN")
    for who in ("student", "admin"):  # its author and a moderator can open it, nobody adds to it
        browser = world.browser(who)
        assert browser.post(f"{POSTS}/{created['id']}/comments", {"body": "x"}).status_code == 403
        assert browser.send("PUT", f"{POSTS}/{created['id']}/reaction").status_code == 403


# --- reactions (COMMUNITY-004, US-10) ---


def test_helpful_once_per_member(world: World, conn: Connection) -> None:  # US-10
    created = post(world.browser("student"))
    reaction = f"{POSTS}/{created['id']}/reaction"
    faculty = world.browser("faculty")
    assert faculty.send("PUT", reaction).json() == {"reacted": True, "reaction_count": 1}
    assert faculty.send("PUT", reaction).json() == {"reacted": True, "reaction_count": 1}
    count = "SELECT count(*) FROM reactions WHERE post_id = :id"
    assert scalar(conn, count, id=created["id"]) == 1  # never duplicated
    assert world.browser("admin").send("PUT", reaction).json()["reaction_count"] == 2
    seen = {p["id"]: p for p in faculty.get(POSTS).json()["items"]}[created["id"]]
    assert seen["reacted"] and seen["reaction_count"] == 2
    assert not world.browser("student").get(f"{POSTS}/{created['id']}").json()["reacted"]
    # Toggling off.
    assert faculty.send("DELETE", reaction).json() == {"reacted": False, "reaction_count": 1}
    assert faculty.send("DELETE", reaction).json() == {"reacted": False, "reaction_count": 1}


def test_reactions_follow_the_post(world: World) -> None:
    created = post(world.browser("student"), SECRET, "DEPARTMENT")
    for who in ("mech_student", "river_admin"):
        not_found(world.browser(who).send("PUT", f"{POSTS}/{created['id']}/reaction"))


# --- limits (COMMUNITY-008) ---


def test_ten_posts_an_hour_then_429(world: World, clock: Clock) -> None:
    student = world.browser("student")
    posts = []
    for n in range(10):
        posts.append(post(student, f"Post {n}"))
        clock.advance(minutes=1)
    assert (
        student.send("DELETE", f"{POSTS}/{posts[0]['id']}").status_code == 204
    )  # doesn't free a slot
    refused = student.post(POSTS, {"body": "One more", "visibility": "COLLEGE"})
    assert refused.status_code == 429
    assert refused.headers["Retry-After"] == str(50 * 60)  # the first leaves the hour then
    post(world.browser("faculty"))  # per member
    clock.advance(minutes=50)
    post(world.browser("student"), "Now it fits")


def test_sixty_comments_an_hour_then_429(world: World, clock: Clock) -> None:
    created = post(world.browser("student"))
    comments = f"{POSTS}/{created['id']}/comments"
    faculty = world.browser("faculty")
    for n in range(60):
        assert faculty.post(comments, {"body": f"Comment {n}"}).status_code == 201
    refused = faculty.post(comments, {"body": "One more"})
    assert refused.status_code == 429 and error_of(refused)["code"] == "rate_limited"
    assert world.browser("admin").post(comments, {"body": "Mine"}).status_code == 201


# --- a fixed number of queries per feed page ---


@pytest.fixture
def statements(conn: Connection) -> Iterator[list[str]]:
    seen: list[str] = []

    def count(*args: Any) -> None:
        seen.append(str(args[2]))

    event.listen(conn, "before_cursor_execute", count)
    yield seen
    event.remove(conn, "before_cursor_execute", count)


def test_a_feed_page_costs_the_same_however_many_posts(
    world: World, clock: Clock, statements: list[str]
) -> None:
    def cost() -> int:
        student = world.browser("student")
        statements.clear()
        assert student.get(POSTS).status_code == 200
        return len(statements)

    for who in ("faculty", "admin"):
        p = post(world.browser(who))
        world.browser("student").send("PUT", f"{POSTS}/{p['id']}/reaction")
    few = cost()
    for n in range(12):
        p = post(world.browser(("faculty", "admin", "staff", "dept_admin")[n % 4]), SECRET + str(n))
        world.browser("mech_student").post(f"{POSTS}/{p['id']}/comments", {"body": "Nice"})
    many = cost()
    assert few == many, (few, many)
