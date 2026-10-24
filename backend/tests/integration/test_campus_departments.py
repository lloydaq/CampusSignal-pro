"""Departments (DEPT-001): college admins create, rename, describe and archive them; every
member can list them. Codes are unique per college and permanent."""

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from tests.integration.auth_helpers import error_of, scalar
from tests.integration.campus_world import CAMPUS, World, build_world

pytestmark = pytest.mark.integration

DEPARTMENTS = f"{CAMPUS}/departments"


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    return build_world(session, app_factory())


def test_members_list_their_own_colleges_departments(world: World) -> None:
    body = world.browser("student").get(DEPARTMENTS).json()
    assert [(d["code"], d["name"]) for d in body["items"]] == [
        ("CSE", "CSE department"),
        ("MECH", "MECH department"),
    ]
    assert {d["id"] for d in body["items"]} == {str(d.id) for d in world.north.departments.values()}


def test_a_college_admin_creates_a_department(world: World, conn: Connection) -> None:
    admin = world.browser("admin")
    response = admin.post(
        DEPARTMENTS,
        {"code": "EEE", "name": "Electrical Engineering", "description": "Labs in block C."},
    )
    assert response.status_code == 201
    assert response.json()["code"] == "EEE"
    assert (
        scalar(
            conn,
            "SELECT count(*) FROM audit_log "
            "WHERE action = 'college.department_created' AND college_id = :c",
            c=world.north.id,
        )
        == 1
    )

    taken = admin.post(DEPARTMENTS, {"code": "eee", "name": "Again"})  # codes are upper-cased
    assert taken.status_code == 409
    assert error_of(taken)["code"] == "code_taken"


def test_the_same_code_can_exist_in_another_college(world: World) -> None:
    assert (
        world.browser("river_admin").post(DEPARTMENTS, {"code": "MECH2", "name": "x"}).status_code
        == 201
    )
    assert (
        world.browser("admin").post(DEPARTMENTS, {"code": "MECH2", "name": "x"}).status_code == 201
    )


@pytest.mark.parametrize("who", ["dept_admin", "faculty", "student"])
def test_only_college_admins_create_or_edit(world: World, who: str) -> None:
    browser = world.browser(who)
    response = browser.post(DEPARTMENTS, {"code": "EEE", "name": "x"})
    assert response.status_code == 403
    assert error_of(response)["code"] == "forbidden"
    cse = world.north.departments["CSE"].id
    assert browser.patch(f"{DEPARTMENTS}/{cse}", {"name": "Hacked"}).status_code == 403


def test_rename_describe_and_archive(world: World) -> None:
    admin = world.browser("admin")
    mech = world.north.departments["MECH"].id
    body = admin.patch(
        f"{DEPARTMENTS}/{mech}", {"name": "Mechanical Engineering", "description": "Workshop."}
    ).json()
    assert (body["name"], body["description"], body["code"]) == (
        "Mechanical Engineering",
        "Workshop.",
        "MECH",
    )
    assert admin.patch(f"{DEPARTMENTS}/{mech}", {"archived": True}).json()["archived"] is True
    # Archived departments drop out of members' lists; admins can ask for them.
    assert [d["code"] for d in world.browser("student").get(DEPARTMENTS).json()["items"]] == ["CSE"]
    assert [d["code"] for d in admin.get(DEPARTMENTS, include_archived="true").json()["items"]] == [
        "CSE",
        "MECH",
    ]
    assert admin.patch(f"{DEPARTMENTS}/{mech}", {"code": "ME"}).status_code == 422  # permanent


def test_another_colleges_department_is_404(world: World) -> None:
    river_cse = world.river.departments["CSE"].id
    admin = world.browser("admin")
    for response in (
        admin.get(f"{DEPARTMENTS}/{river_cse}"),
        admin.patch(f"{DEPARTMENTS}/{river_cse}", {"name": "Hacked"}),
    ):
        assert response.status_code == 404
        assert "Riverside" not in response.text and "CSE department" not in response.text


@pytest.mark.parametrize("code", ["", "has space", "x" * 17, "-LEAD"])
def test_invalid_codes_are_422(world: World, code: str) -> None:
    response = world.browser("admin").post(DEPARTMENTS, {"code": code, "name": "x"})
    assert response.status_code == 422
