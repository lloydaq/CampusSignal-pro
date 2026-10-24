"""Roster import (MEMBER-001): a CSV validated row by row, imported all-or-nothing, reporting
every problem with its row number. College admins only."""

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from tests.integration.auth_helpers import error_of, scalar
from tests.integration.campus_world import CAMPUS, World, build_world

pytestmark = pytest.mark.integration

IMPORT = f"{CAMPUS}/roster/import"
ROSTER = f"{CAMPUS}/roster"
HEADER = "roll_number,full_name,department_code,program,admission_year,email"


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    return build_world(session, app_factory())


def roster_count(conn: Connection, world: World) -> int:
    return int(
        scalar(conn, "SELECT count(*) FROM roster_entries WHERE college_id = :c", c=world.north.id)
    )


def test_a_valid_csv_is_imported_and_audited(world: World, conn: Connection) -> None:
    csv = "\n".join(
        [
            HEADER,
            "N-100,Diya Rao,CSE,B.Tech,2025,diya@northfield.example",
            "N-101,  Kabir  Shah ,mech,B.Tech,2025,",
            "",
        ]
    )
    response = world.browser("admin").post(IMPORT, {"csv": csv})
    assert response.status_code == 201
    assert response.json() == {"imported": 2}
    assert roster_count(conn, world) == 4
    entry = conn.exec_driver_sql(
        "SELECT full_name, email, department_id FROM roster_entries WHERE roll_number = 'N-101'"
    ).one()
    assert entry.full_name == "Kabir Shah"
    assert entry.email is None
    assert entry.department_id == world.north.departments["MECH"].id
    audit = conn.exec_driver_sql(
        "SELECT metadata FROM audit_log WHERE action = 'college.roster_imported'"
    ).scalar()
    assert audit == {"rows": 2}  # counts only, no names or roll numbers


def test_any_bad_row_rejects_the_whole_file_with_every_problem_listed(
    world: World, conn: Connection
) -> None:
    csv = "\n".join(
        [
            HEADER,
            "N-200,Good Row,CSE,B.Tech,2025,good@northfield.example",
            "N-001,Already There,CSE,B.Tech,2025,",  # on the roster already
            "N-201,No Dept,EEE,B.Tech,2025,",  # unknown department
            "N-202,Bad Year,CSE,B.Tech,20x5,",
            "N-203,Bad Email,CSE,B.Tech,2025,not-an-email",
            "N-200,Duplicate In File,CSE,B.Tech,2025,",
            ",Missing Roll,CSE,B.Tech,2025,",
        ]
    )
    response = world.browser("admin").post(IMPORT, {"csv": csv})
    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "roster_invalid"
    assert [(d["row"], d["column"]) for d in error["details"]] == [
        (3, "roll_number"),
        (4, "department_code"),
        (5, "admission_year"),
        (6, "email"),
        (7, "roll_number"),
        (8, "roll_number"),
    ]
    assert roster_count(conn, world) == 2  # nothing imported


def test_another_colleges_department_code_is_unknown_here(
    world: World, session: Session, conn: Connection
) -> None:
    from app.models import Department

    session.add(Department(college_id=world.river.id, code="RIV", name="Riverside only"))
    session.commit()
    response = world.browser("admin").post(IMPORT, {"csv": f"{HEADER}\nN-300,X,RIV,B.Tech,2025,"})
    assert response.status_code == 422
    assert error_of(response)["details"][0]["column"] == "department_code"


@pytest.mark.parametrize(
    ("csv", "message_part"),
    [
        ("", "empty"),
        ("roll_number,full_name\nN-1,X", "columns"),
        (HEADER, "no rows"),
    ],
)
def test_malformed_files_are_422(world: World, csv: str, message_part: str) -> None:
    response = world.browser("admin").post(IMPORT, {"csv": csv})
    assert response.status_code == 422
    assert message_part in str(error_of(response)).lower()


def test_archived_departments_take_no_new_rows(world: World) -> None:
    admin = world.browser("admin")
    admin.patch(f"{CAMPUS}/departments/{world.north.departments['MECH'].id}", {"archived": True})
    response = admin.post(IMPORT, {"csv": f"{HEADER}\nN-400,X,MECH,B.Tech,2025,"})
    assert response.status_code == 422


@pytest.mark.parametrize("who", ["dept_admin", "faculty", "student"])
def test_only_college_admins_import_or_read_the_roster(
    world: World, who: str, conn: Connection
) -> None:
    browser = world.browser(who)
    assert browser.post(IMPORT, {"csv": f"{HEADER}\nN-500,X,CSE,B.Tech,2025,"}).status_code == 403
    response = browser.get(ROSTER)
    assert response.status_code == 403
    assert "N-001" not in response.text
    assert roster_count(conn, world) == 2


def test_the_roster_list_shows_this_college_only_with_claim_state(world: World) -> None:
    body = world.browser("admin").get(ROSTER).json()
    rows = {r["roll_number"]: r for r in body["items"]}
    assert set(rows) == {"N-001", "N-002"}  # never R-001
    assert rows["N-001"]["claimed"] is True
    assert rows["N-001"]["department"]["code"] == "CSE"
    assert (
        world.browser("admin").get(ROSTER, query="n-002").json()["items"][0]["roll_number"]
        == "N-002"
    )
