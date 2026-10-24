"""Member directory, member changes and role grants (ADMIN-003, DEPT-002, MEMBER-011, US-14,
PRD §17.6 and §17.12)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from tests.integration.auth_helpers import PREFIX, error_of, scalar
from tests.integration.campus_world import CAMPUS, World, build_world

pytestmark = pytest.mark.integration

MEMBERS = f"{CAMPUS}/members"


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    return build_world(session, app_factory())


def names(page: dict[str, Any]) -> list[str]:
    return sorted(m["display_name"] for m in page["items"])


# --- directory ------------------------------------------------------------------------------


def test_a_college_admin_sees_every_member_with_contact_details(world: World) -> None:
    page = world.browser("admin").get(MEMBERS).json()
    assert names(page) == ["Admin", "Dept Admin", "Faculty", "Mech Student", "Student"]
    student = next(m for m in page["items"] if m["display_name"] == "Student")
    assert student["email"] == "student@northfield.example"
    assert student["roll_number"] == "N-001"
    assert student["department"]["code"] == "CSE"
    assert "River" not in str(page)


def test_a_department_admin_sees_own_department_students_and_college_staff(world: World) -> None:
    page = world.browser("dept_admin").get(MEMBERS).json()
    assert names(page) == ["Admin", "Dept Admin", "Faculty", "Student"]  # not the MECH student
    by_name = {m["display_name"]: m for m in page["items"]}
    assert by_name["Student"]["email"] == "student@northfield.example"  # own department student
    assert by_name["Student"]["roll_number"] == "N-001"
    assert by_name["Faculty"]["email"] is None  # §17.6: not a student of their department
    assert by_name["Faculty"]["roll_number"] is None


@pytest.mark.parametrize("who", ["faculty", "student"])
def test_others_have_no_directory(world: World, who: str) -> None:
    response = world.browser(who).get(MEMBERS)
    assert response.status_code == 403  # §17.12: no member enumeration
    assert "Mech Student" not in response.text


def test_directory_filters(world: World) -> None:
    admin = world.browser("admin")
    assert names(admin.get(MEMBERS, kind="STUDENT").json()) == ["Mech Student", "Student"]
    assert names(admin.get(MEMBERS, query="mech").json()) == ["Mech Student"]
    assert names(admin.get(MEMBERS, query="N-002").json()) == [
        "Mech Student"
    ]  # admins: roll number
    assert (
        names(world.browser("dept_admin").get(MEMBERS, query="student@northfield").json()) == []
    )  # name only


def test_the_directory_pages_with_a_cursor(world: World) -> None:
    admin = world.browser("admin")
    first = admin.get(MEMBERS, limit=2).json()
    second = admin.get(MEMBERS, limit=2, cursor=first["next_cursor"]).json()
    third = admin.get(MEMBERS, limit=2, cursor=second["next_cursor"]).json()
    seen = [m["id"] for page in (first, second, third) for m in page["items"]]
    assert len(seen) == len(set(seen)) == 5
    assert third["next_cursor"] is None


# --- changing a membership ------------------------------------------------------------------


def member_path(world: World, who: str) -> str:
    return f"{MEMBERS}/{world.members[who].id}"


def test_suspend_reactivate_and_end_a_member(world: World, conn: Connection) -> None:
    admin, student = world.browser("admin"), world.browser("student")
    path = member_path(world, "student")
    assert admin.patch(path, {"status": "SUSPENDED"}).status_code == 422  # reason required
    assert (
        admin.patch(path, {"status": "SUSPENDED", "reason": "Disciplinary hold"}).json()["status"]
        == "SUSPENDED"
    )
    assert student.get(f"{PREFIX}/me").json()["capabilities"] == []
    assert admin.patch(path, {"status": "ACTIVE"}).json()["status"] == "ACTIVE"
    assert admin.patch(path, {"status": "ENDED", "reason": "Graduated"}).json()["status"] == "ENDED"
    assert admin.patch(path, {"status": "ACTIVE"}).status_code == 409  # ended is final
    actions = scalar(
        conn,
        "SELECT array_agg(action ORDER BY created_at) FROM audit_log WHERE target_id = :t",
        t=str(world.members["student"].id),
    )
    assert actions == [
        "college.membership_suspended",
        "college.membership_reactivated",
        "college.membership_ended",
    ]


def test_change_a_members_department(world: World) -> None:
    mech = world.north.departments["MECH"].id
    body = (
        world.browser("admin")
        .patch(member_path(world, "faculty"), {"department_id": str(mech)})
        .json()
    )
    assert body["department"]["code"] == "MECH"
    river_cse = world.river.departments["CSE"].id
    assert (
        world.browser("admin")
        .patch(member_path(world, "faculty"), {"department_id": str(river_cse)})
        .status_code
        == 404
    )


def test_the_last_college_admin_cannot_be_suspended_or_ended(world: World) -> None:
    admin = world.browser("admin")
    for change in ({"status": "SUSPENDED", "reason": "x"}, {"status": "ENDED", "reason": "x"}):
        response = admin.patch(member_path(world, "admin"), change)
        assert response.status_code == 409  # MEMBER-011, US-14
        assert error_of(response)["code"] == "last_college_admin"


@pytest.mark.parametrize("who", ["dept_admin", "faculty", "student"])
def test_only_college_admins_change_members(world: World, who: str) -> None:
    response = world.browser(who).patch(
        member_path(world, "mech_student"), {"status": "ENDED", "reason": "x"}
    )
    assert response.status_code == 403


def test_another_colleges_member_is_404(world: World) -> None:
    response = world.browser("admin").patch(
        member_path(world, "river_student"), {"status": "ENDED", "reason": "x"}
    )
    assert response.status_code == 404
    assert "river" not in response.text.lower()


# --- role grants ----------------------------------------------------------------------------


def grants_path(world: World, who: str) -> str:
    return f"{member_path(world, who)}/grants"


def test_grant_and_revoke_roles(world: World, conn: Connection) -> None:
    admin = world.browser("admin")
    mech = str(world.north.departments["MECH"].id)
    granted = admin.post(
        grants_path(world, "faculty"), {"role": "DEPARTMENT_ADMIN", "department_id": mech}
    )
    assert granted.status_code == 201
    assert granted.json()["department"]["code"] == "MECH"
    assert (
        admin.post(
            grants_path(world, "faculty"), {"role": "DEPARTMENT_ADMIN", "department_id": mech}
        ).status_code
        == 409
    )
    assert (
        admin.post(grants_path(world, "faculty"), {"role": "ISSUE_COORDINATOR"}).status_code == 201
    )

    faculty_me = world.browser("faculty").get(f"{PREFIX}/me").json()
    assert {r["role"] for r in faculty_me["roles"]} == {"DEPARTMENT_ADMIN", "ISSUE_COORDINATOR"}

    revoked = admin.send("DELETE", f"{grants_path(world, 'faculty')}/{granted.json()['id']}")
    assert revoked.status_code == 204
    assert (
        scalar(
            conn,
            "SELECT count(*) FROM audit_log "
            "WHERE action IN ('college.role_granted', 'college.role_revoked')",
        )
        == 3
    )


def test_students_cannot_hold_roles(world: World) -> None:
    response = world.browser("admin").post(
        grants_path(world, "student"), {"role": "ISSUE_COORDINATOR"}
    )
    assert response.status_code == 422  # US-14
    assert error_of(response)["code"] == "student_cannot_hold_roles"


@pytest.mark.parametrize(
    "body",
    [
        {"role": "DEPARTMENT_ADMIN"},  # needs a department
        {"role": "COLLEGE_ADMIN", "department_id": "00000000-0000-0000-0000-000000000000"},
        {"role": "PLATFORM_ADMIN"},
    ],
)
def test_malformed_grants_are_422(world: World, body: dict[str, str]) -> None:
    assert world.browser("admin").post(grants_path(world, "faculty"), body).status_code == 422


def test_a_department_of_another_college_is_404(world: World) -> None:
    river_cse = str(world.river.departments["CSE"].id)
    response = world.browser("admin").post(
        grants_path(world, "faculty"), {"role": "DEPARTMENT_ADMIN", "department_id": river_cse}
    )
    assert response.status_code == 404


def test_the_last_college_admin_grant_cannot_be_revoked(world: World) -> None:
    admin = world.browser("admin")
    # Grant ids come from the directory (/me lists roles without ids).
    directory = admin.get(MEMBERS).json()["items"]
    grant = next(m for m in directory if m["display_name"] == "Admin")["roles"][0]
    response = admin.send("DELETE", f"{grants_path(world, 'admin')}/{grant['id']}")
    assert response.status_code == 409
    assert error_of(response)["code"] == "last_college_admin"

    # With a second admin, the first can step down.
    assert admin.post(grants_path(world, "faculty"), {"role": "COLLEGE_ADMIN"}).status_code == 201
    assert admin.send("DELETE", f"{grants_path(world, 'admin')}/{grant['id']}").status_code == 204


@pytest.mark.parametrize("who", ["dept_admin", "faculty", "student"])
def test_only_college_admins_grant(world: World, who: str) -> None:
    assert (
        world.browser(who)
        .post(grants_path(world, "faculty"), {"role": "COLLEGE_ADMIN"})
        .status_code
        == 403
    )


def test_inactive_members_get_no_new_roles(world: World) -> None:
    admin = world.browser("admin")
    admin.patch(member_path(world, "faculty"), {"status": "SUSPENDED", "reason": "x"})
    response = admin.post(grants_path(world, "faculty"), {"role": "ISSUE_COORDINATOR"})
    assert response.status_code == 409
    assert error_of(response)["code"] == "membership_inactive"
