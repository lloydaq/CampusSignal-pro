"""Faculty/staff invites from college admins (MEMBER-007) and the college audit log
(ADMIN-007, US-14)."""

import re
from collections.abc import Callable

import pytest
from fastapi import FastAPI
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from app.core.mailer import InMemoryMailer
from tests.integration.auth_helpers import PREFIX, error_of
from tests.integration.campus_world import CAMPUS, World, build_world
from tests.integration.platform_helpers import Browser
from tests.integration.tenancy import make_user

pytestmark = pytest.mark.integration

INVITES = f"{CAMPUS}/invites"
AUDIT = f"{CAMPUS}/audit-log"
TOKEN_RE = re.compile(r"/invites/accept#token=([A-Za-z0-9_-]+)")


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    return build_world(session, app_factory())


@pytest.fixture
def mailer(world: World) -> InMemoryMailer:
    m = world.app.state.mailer
    assert isinstance(m, InMemoryMailer)
    m.outbox.clear()
    return m


def test_a_college_admin_invites_staff_who_then_joins(
    world: World, session: Session, mailer: InMemoryMailer
) -> None:
    admin = world.browser("admin")
    response = admin.post(INVITES, {"email": "librarian@northfield.example", "kind": "STAFF"})
    assert response.status_code == 201
    assert response.json()["state"] == "PENDING"
    token = TOKEN_RE.search(mailer.outbox[0].text)
    assert token

    make_user(session, "librarian@northfield.example", verified=False)
    session.commit()
    librarian = Browser(world.app, "librarian@northfield.example")
    assert librarian.post("/api/v1/invites/accept", {"token": token.group(1)}).status_code == 200
    me = librarian.get(f"{PREFIX}/me").json()
    assert (me["membership"]["kind"], me["roles"]) == ("STAFF", [])
    assert [
        i["email"] for i in admin.get(INVITES).json()["items"]
    ] == []  # accepted: no longer pending


def test_inviting_a_current_member_is_409(world: World) -> None:
    response = world.browser("admin").post(
        INVITES, {"email": "faculty@northfield.example", "kind": "FACULTY"}
    )
    assert response.status_code == 409
    assert error_of(response)["code"] == "already_member"


def test_students_are_not_invited(world: World) -> None:
    assert (
        world.browser("admin")
        .post(INVITES, {"email": "x@northfield.example", "kind": "STUDENT"})
        .status_code
        == 422
    )


@pytest.mark.parametrize("who", ["dept_admin", "faculty", "student"])
def test_only_college_admins_invite_or_see_invites(world: World, who: str) -> None:
    browser = world.browser(who)
    assert (
        browser.post(INVITES, {"email": "x@northfield.example", "kind": "STAFF"}).status_code == 403
    )
    assert browser.get(INVITES).status_code == 403


def test_pending_invites_list_only_this_college(world: World) -> None:
    world.browser("admin").post(INVITES, {"email": "a@northfield.example", "kind": "STAFF"})
    world.browser("river_admin").post(INVITES, {"email": "b@riverside.example", "kind": "STAFF"})
    assert [i["email"] for i in world.browser("admin").get(INVITES).json()["items"]] == [
        "a@northfield.example"
    ]


# --- audit log ------------------------------------------------------------------------------


def test_the_college_audit_log_shows_only_this_colleges_entries(
    world: World, conn: Connection
) -> None:
    world.browser("admin").post(f"{CAMPUS}/departments", {"code": "EEE", "name": "Electrical"})
    world.browser("river_admin").post(
        f"{CAMPUS}/departments", {"code": "RIV", "name": "Riverside only"}
    )
    conn.exec_driver_sql("INSERT INTO audit_log (action) VALUES ('auth.password_changed')")

    page = world.browser("admin").get(AUDIT).json()
    assert [e["action"] for e in page["items"]] == ["college.department_created"]  # US-14
    assert "RIV" not in str(page)
    assert page["items"][0]["actor"]["display_name"] == "Admin"


def test_the_audit_log_filters_by_action_and_actor(world: World) -> None:
    admin = world.browser("admin")
    admin.post(f"{CAMPUS}/departments", {"code": "EEE", "name": "Electrical"})
    admin.post(INVITES, {"email": "a@northfield.example", "kind": "STAFF"})
    assert [
        e["action"] for e in admin.get(AUDIT, action="college.invite_sent").json()["items"]
    ] == ["college.invite_sent"]
    actor = str(world.members["admin"].user_id)
    assert len(admin.get(AUDIT, actor_user_id=actor).json()["items"]) == 2
    assert (
        admin.get(AUDIT, actor_user_id=str(world.members["faculty"].user_id)).json()["items"] == []
    )


@pytest.mark.parametrize("who", ["dept_admin", "faculty", "student"])
def test_only_college_admins_read_the_audit_log(world: World, who: str) -> None:
    assert world.browser(who).get(AUDIT).status_code == 403
