"""Academic setup (ACADEMIC-001…004, US-13): terms, subjects, sections, instructors, enrollment
and the timetable, with the access matrix of PRD §11 (ACADEMIC-010)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from app.models import MembershipKind, MembershipStatus
from tests.integration.auth_helpers import error_of, scalar
from tests.integration.campus_world import CAMPUS, World, build_world
from tests.integration.tenancy import add_member, make_user, roster_entry

pytestmark = pytest.mark.integration

TERMS = f"{CAMPUS}/terms"
SUBJECTS = f"{CAMPUS}/subjects"
SECTIONS = f"{CAMPUS}/sections"
NOT_FOUND = {"code": "not_found", "message": "Not found.", "details": None}


def not_found(response: Any) -> bool:
    error = error_of(response)
    return response.status_code == 404 and {k: error[k] for k in NOT_FOUND} == NOT_FOUND


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    return build_world(session, app_factory())


def created(response: Any) -> dict[str, Any]:
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def make_term(world: World, name: str = "2026-27 Odd", *, current: bool = True) -> dict[str, Any]:
    return created(
        world.browser("admin").post(
            TERMS,
            {
                "name": name,
                "starts_on": "2026-07-01",
                "ends_on": "2026-12-15",
                "is_current": current,
            },
        )
    )


def make_subject(world: World, code: str, department: str = "CSE") -> dict[str, Any]:
    return created(
        world.browser("admin").post(
            SUBJECTS,
            {
                "department_id": str(world.north.departments[department].id),
                "code": code,
                "name": f"{code} subject",
            },
        )
    )


def make_section(
    world: World, term: dict[str, Any], subject: dict[str, Any], name: str = "A"
) -> dict[str, Any]:
    return created(
        world.browser("admin").post(
            SECTIONS, {"term_id": term["id"], "subject_id": subject["id"], "name": name}
        )
    )


@pytest.fixture
def cse(world: World) -> dict[str, Any]:
    """A current term, a CSE subject with section A taught by `faculty`, and a MECH section."""
    term = make_term(world)
    section = make_section(world, term, make_subject(world, "CS301"))
    mech = make_section(world, term, make_subject(world, "ME201", "MECH"))
    assigned = world.browser("admin").send(
        "PUT",
        f"{SECTIONS}/{section['id']}/instructors",
        {"membership_ids": [str(world.members["faculty"].id)]},
    )
    assert assigned.status_code == 200, assigned.text
    return {"term": term, "section": assigned.json(), "mech": mech}


# --- terms ---------------------------------------------------------------------------------


def test_one_current_term_per_college(world: World) -> None:
    admin = world.browser("admin")
    first = make_term(world)
    assert first["is_current"] is True

    second = admin.post(
        TERMS,
        {
            "name": "2027 Even",
            "starts_on": "2027-01-05",
            "ends_on": "2027-05-30",
            "is_current": True,
        },
    )
    assert second.status_code == 409
    assert error_of(second)["code"] == "current_term_exists"

    later = make_term(world, "2027 Even", current=False)
    moved = admin.patch(f"{TERMS}/{later['id']}", {"is_current": True})
    assert moved.status_code == 409
    assert admin.patch(f"{TERMS}/{first['id']}", {"is_current": False}).status_code == 200
    assert admin.patch(f"{TERMS}/{later['id']}", {"is_current": True}).json()["is_current"] is True

    # Riverside's own current term is unaffected by Northfield's.
    assert (
        world.browser("river_admin")
        .post(
            TERMS,
            {"name": "R", "starts_on": "2026-07-01", "ends_on": "2026-12-01", "is_current": True},
        )
        .status_code
        == 201
    )


def test_term_dates_and_names(world: World) -> None:
    admin = world.browser("admin")
    backwards = admin.post(TERMS, {"name": "X", "starts_on": "2026-12-01", "ends_on": "2026-07-01"})
    assert backwards.status_code == 422
    term = make_term(world)
    assert admin.patch(f"{TERMS}/{term['id']}", {"ends_on": "2026-06-01"}).status_code == 422
    duplicate = admin.post(
        TERMS, {"name": term["name"], "starts_on": "2027-01-01", "ends_on": "2027-05-01"}
    )
    assert duplicate.status_code == 409
    assert error_of(duplicate)["code"] == "term_name_taken"


@pytest.mark.parametrize("who", ["dept_admin", "faculty", "student"])
def test_only_college_admins_create_or_change_terms(world: World, who: str) -> None:
    term = make_term(world)
    browser = world.browser(who)
    body = {"name": "X", "starts_on": "2027-01-01", "ends_on": "2027-05-01"}
    assert browser.post(TERMS, body).status_code == 403
    assert browser.patch(f"{TERMS}/{term['id']}", {"name": "Hacked"}).status_code == 403


def test_terms_are_listed_for_catalog_managers_only(world: World) -> None:
    make_term(world)
    assert [t["name"] for t in world.browser("dept_admin").get(TERMS).json()["items"]] == [
        "2026-27 Odd"
    ]
    for who in ("faculty", "student"):
        assert world.browser(who).get(TERMS).status_code == 403


def test_a_riverside_term_is_not_found(world: World) -> None:
    river = created(
        world.browser("river_admin").post(
            TERMS, {"name": "R", "starts_on": "2026-07-01", "ends_on": "2026-12-01"}
        )
    )
    assert not_found(world.browser("admin").patch(f"{TERMS}/{river['id']}", {"name": "Hacked"}))


# --- subjects ------------------------------------------------------------------------------


def test_department_admins_manage_subjects_of_their_departments_only(world: World) -> None:
    dept_admin = world.browser("dept_admin")
    cse = created(
        dept_admin.post(
            SUBJECTS,
            {
                "department_id": str(world.north.departments["CSE"].id),
                "code": "cs101",
                "name": "Programming",
            },
        )
    )
    assert cse["code"] == "CS101"
    assert cse["department"]["code"] == "CSE"
    mech = dept_admin.post(
        SUBJECTS,
        {"department_id": str(world.north.departments["MECH"].id), "code": "ME101", "name": "x"},
    )
    assert not_found(mech)
    river = dept_admin.post(
        SUBJECTS,
        {"department_id": str(world.river.departments["CSE"].id), "code": "RV101", "name": "x"},
    )
    assert not_found(river)

    other = make_subject(world, "ME201", "MECH")
    assert not_found(dept_admin.patch(f"{SUBJECTS}/{other['id']}", {"name": "Hacked"}))
    assert not_found(dept_admin.send("DELETE", f"{SUBJECTS}/{other['id']}"))
    listed = dept_admin.get(SUBJECTS).json()["items"]
    assert [s["code"] for s in listed] == ["CS101"]
    assert {s["code"] for s in world.browser("admin").get(SUBJECTS).json()["items"]} == {
        "CS101",
        "ME201",
    }

    renamed = dept_admin.patch(f"{SUBJECTS}/{cse['id']}", {"name": "Programming I"})
    assert renamed.json()["name"] == "Programming I"


def test_subject_codes_are_unique_per_college(world: World) -> None:
    make_subject(world, "CS301")
    again = world.browser("admin").post(
        SUBJECTS,
        {"department_id": str(world.north.departments["MECH"].id), "code": "CS301", "name": "x"},
    )
    assert again.status_code == 409
    assert error_of(again)["code"] == "code_taken"
    assert (
        world.browser("river_admin")
        .post(
            SUBJECTS,
            {"department_id": str(world.river.departments["CSE"].id), "code": "CS301", "name": "x"},
        )
        .status_code
        == 201
    )


@pytest.mark.parametrize("who", ["faculty", "student"])
def test_faculty_and_students_do_not_manage_subjects(world: World, who: str) -> None:
    subject = make_subject(world, "CS301")
    browser = world.browser(who)
    body = {"department_id": str(world.north.departments["CSE"].id), "code": "X1", "name": "x"}
    assert browser.post(SUBJECTS, body).status_code == 403
    assert browser.get(SUBJECTS).status_code == 403
    assert browser.patch(f"{SUBJECTS}/{subject['id']}", {"name": "x"}).status_code == 403
    assert browser.send("DELETE", f"{SUBJECTS}/{subject['id']}").status_code == 403


def test_a_subject_with_sections_cannot_be_deleted(world: World) -> None:
    term = make_term(world)
    subject = make_subject(world, "CS301")
    section = make_section(world, term, subject)
    admin = world.browser("admin")
    blocked = admin.send("DELETE", f"{SUBJECTS}/{subject['id']}")
    assert blocked.status_code == 409
    assert error_of(blocked)["code"] == "subject_in_use"
    assert admin.send("DELETE", f"{SECTIONS}/{section['id']}").status_code == 204
    assert admin.send("DELETE", f"{SUBJECTS}/{subject['id']}").status_code == 204


# --- sections and instructors --------------------------------------------------------------


def test_a_department_admin_cannot_create_a_section_in_another_department(world: World) -> None:
    """US-13: another department's subject → 404."""
    term = make_term(world)
    mech = make_subject(world, "ME201", "MECH")
    response = world.browser("dept_admin").post(
        SECTIONS, {"term_id": term["id"], "subject_id": mech["id"], "name": "A"}
    )
    assert not_found(response)


def test_sections_are_created_named_and_listed(world: World, cse: dict[str, Any]) -> None:
    section = cse["section"]
    assert section["subject"]["code"] == "CS301"
    assert section["term"]["is_current"] is True
    assert section["department"]["code"] == "CSE"
    assert [i["display_name"] for i in section["instructors"]] == ["Faculty"]
    assert section["enrollment_count"] == 0

    again = world.browser("dept_admin").post(
        SECTIONS,
        {"term_id": cse["term"]["id"], "subject_id": section["subject"]["id"], "name": "A"},
    )
    assert again.status_code == 409
    assert error_of(again)["code"] == "section_exists"

    listed = world.browser("dept_admin").get(SECTIONS).json()["items"]
    assert [s["id"] for s in listed] == [section["id"]]  # not the MECH section
    assert len(world.browser("admin").get(SECTIONS).json()["items"]) == 2


def test_section_reads_follow_the_access_matrix(world: World, cse: dict[str, Any]) -> None:
    path = f"{SECTIONS}/{cse['section']['id']}"
    for who in ("admin", "dept_admin", "faculty"):
        assert world.browser(who).get(path).status_code == 200, who
    # A department admin of CSE doesn't see MECH's section; faculty not assigned get 404.
    assert not_found(world.browser("dept_admin").get(f"{SECTIONS}/{cse['mech']['id']}"))
    assert not_found(world.browser("faculty").get(f"{SECTIONS}/{cse['mech']['id']}"))
    student = world.browser("student").get(path)
    assert student.status_code == 403
    assert "CS301" not in student.text
    assert world.browser("faculty").get(SECTIONS).status_code == 403
    assert world.browser("faculty").patch(path, {"name": "B"}).status_code == 403


def test_only_active_faculty_of_the_college_are_assigned(
    world: World, cse: dict[str, Any], session: Session
) -> None:
    path = f"{SECTIONS}/{cse['section']['id']}/instructors"
    suspended = add_member(
        session,
        make_user(session, "gone@northfield.example"),
        world.north,
        MembershipKind.FACULTY,
        status=MembershipStatus.SUSPENDED,
    )
    session.commit()
    bad = [
        world.members["student"].id,  # a student
        world.members["dept_admin"].id,  # staff
        world.members["river_admin"].id,  # Riverside faculty
        suspended.id,
    ]
    response = world.browser("admin").send(
        "PUT", path, {"membership_ids": [str(world.members["admin"].id)] + [str(b) for b in bad]}
    )
    assert response.status_code == 422
    assert [d["field"] for d in error_of(response)["details"]] == [
        "membership_ids.1",
        "membership_ids.2",
        "membership_ids.3",
        "membership_ids.4",
    ]
    assert "River" not in response.text
    # Nothing changed.
    section = world.browser("admin").get(f"{SECTIONS}/{cse['section']['id']}").json()
    assert [i["display_name"] for i in section["instructors"]] == ["Faculty"]

    replaced = world.browser("dept_admin").send(
        "PUT", path, {"membership_ids": [str(world.members["admin"].id)]}
    )
    assert [i["display_name"] for i in replaced.json()["instructors"]] == ["Admin"]
    assert not_found(world.browser("faculty").get(f"{SECTIONS}/{cse['section']['id']}"))


def test_teaching_sections_lists_the_current_terms_assigned_sections(
    world: World, cse: dict[str, Any]
) -> None:
    body = world.browser("faculty").get(f"{CAMPUS}/teaching/sections").json()
    assert body["term"]["id"] == cse["term"]["id"]
    assert [s["id"] for s in body["items"]] == [cse["section"]["id"]]
    assert world.browser("admin").get(f"{CAMPUS}/teaching/sections").json()["items"] == []
    for who in ("student", "dept_admin"):
        assert world.browser(who).get(f"{CAMPUS}/teaching/sections").status_code == 403


# --- enrollments ---------------------------------------------------------------------------


def import_csv(world: World, who: str, section_id: str, csv: str) -> Any:
    return world.browser(who).post(f"{SECTIONS}/{section_id}/enrollments/import", {"csv": csv})


def test_enrollment_csv_is_all_or_nothing(
    world: World, cse: dict[str, Any], session: Session, conn: Connection
) -> None:
    """US-13: unknown or non-student roll numbers → 422 listing the rows; nothing enrolled."""
    roster_entry(session, world.north, "N-003")  # on the roster, nobody claimed it
    roster_entry(session, world.river, "R-777")
    session.commit()
    section_id = cse["section"]["id"]
    response = import_csv(
        world, "dept_admin", section_id, "roll_number\nn-001\nN-999\nN-003\nR-777\nN-001\n"
    )
    assert response.status_code == 422
    assert error_of(response)["code"] == "enrollment_invalid"
    assert [d["row"] for d in error_of(response)["details"]] == [3, 4, 5, 6]
    assert scalar(conn, "SELECT count(*) FROM enrollments") == 0

    ok = import_csv(world, "dept_admin", section_id, "roll_number\nN-001\nN-002\n")
    assert ok.json() == {"enrolled": 2, "already_enrolled": 0}
    again = import_csv(world, "admin", section_id, "﻿roll_number\r\nN-001\r\n")
    assert again.json() == {"enrolled": 0, "already_enrolled": 1}
    # The audit trail has counts, never roll numbers.
    rows = (
        conn.exec_driver_sql(
            "SELECT metadata::text FROM audit_log WHERE action = 'academic.enrollments_added'"
        )
        .scalars()
        .all()
    )
    assert rows and all("N-00" not in r for r in rows)


def test_enrollment_csv_header_and_suspended_students(
    world: World, cse: dict[str, Any], session: Session
) -> None:
    section_id = cse["section"]["id"]
    assert import_csv(world, "admin", section_id, "roll,name\nN-001,x\n").status_code == 422
    world.members["student"].status = MembershipStatus.SUSPENDED
    session.commit()
    response = import_csv(world, "admin", section_id, "roll_number\nN-001\n")
    assert response.status_code == 422


def test_enrolling_by_picking_members(world: World, cse: dict[str, Any]) -> None:
    path = f"{SECTIONS}/{cse['section']['id']}/enrollments"
    admin = world.browser("admin")
    wrong = admin.post(
        path,
        {
            "membership_ids": [
                str(world.members["student"].id),
                str(world.members["faculty"].id),
                str(world.members["river_student"].id),
            ]
        },
    )
    assert wrong.status_code == 422
    assert [d["field"] for d in error_of(wrong)["details"]] == [
        "membership_ids.1",
        "membership_ids.2",
    ]
    added = admin.post(path, {"membership_ids": [str(world.members["student"].id)]})
    assert added.json() == {"enrolled": 1, "already_enrolled": 0}


@pytest.mark.parametrize("who", ["faculty", "student"])
def test_faculty_and_students_do_not_enroll(world: World, cse: dict[str, Any], who: str) -> None:
    section_id = cse["section"]["id"]
    assert import_csv(world, who, section_id, "roll_number\nN-001\n").status_code == 403
    assert (
        world.browser(who)
        .post(
            f"{SECTIONS}/{section_id}/enrollments",
            {"membership_ids": [str(world.members["student"].id)]},
        )
        .status_code
        == 403
    )


def test_enrollment_lists_and_removal(world: World, cse: dict[str, Any]) -> None:
    section_id = cse["section"]["id"]
    import_csv(world, "admin", section_id, "roll_number\nN-001\n")
    path = f"{SECTIONS}/{section_id}/enrollments"

    managed = world.browser("dept_admin").get(path).json()["items"]
    assert [(e["display_name"], e["roll_number"]) for e in managed] == [("Student", "N-001")]
    # Assigned faculty see who is enrolled, but roll numbers stay with admins (PRD §17.6).
    taught = world.browser("faculty").get(path).json()["items"]
    assert [(e["display_name"], e["roll_number"]) for e in taught] == [("Student", None)]
    assert world.browser("student").get(path).status_code == 403
    assert not_found(world.browser("faculty").get(f"{SECTIONS}/{cse['mech']['id']}/enrollments"))

    blocked = world.browser("admin").send("DELETE", f"{SECTIONS}/{section_id}")
    assert blocked.status_code == 409
    assert error_of(blocked)["code"] == "section_has_enrollments"

    enrollment = managed[0]["id"]
    assert (
        world.browser("faculty").send("DELETE", f"{CAMPUS}/enrollments/{enrollment}").status_code
        == 403
    )
    assert (
        world.browser("dept_admin").send("DELETE", f"{CAMPUS}/enrollments/{enrollment}").status_code
        == 204
    )
    assert world.browser("admin").get(path).json()["items"] == []
    assert world.browser("admin").send("DELETE", f"{SECTIONS}/{section_id}").status_code == 204


def test_a_mech_enrollment_is_not_found_for_the_cse_admin(
    world: World, cse: dict[str, Any]
) -> None:
    import_csv(world, "admin", cse["mech"]["id"], "roll_number\nN-002\n")
    enrollment = (
        world.browser("admin").get(f"{SECTIONS}/{cse['mech']['id']}/enrollments").json()["items"][0]
    )
    assert not_found(
        world.browser("dept_admin").send("DELETE", f"{CAMPUS}/enrollments/{enrollment['id']}")
    )


# --- timetable -----------------------------------------------------------------------------


def slot(weekday: int, start: str, end: str, room: str = "B-204") -> dict[str, Any]:
    return {"weekday": weekday, "starts_at": start, "ends_at": end, "room": room}


def test_timetable_entries_of_a_section_never_overlap(world: World, cse: dict[str, Any]) -> None:
    """US-13: an overlapping entry for the same section → 409."""
    path = f"{SECTIONS}/{cse['section']['id']}/timetable"
    dept_admin = world.browser("dept_admin")
    first = created(dept_admin.post(path, slot(1, "09:00", "10:00")))
    overlap = dept_admin.post(path, slot(1, "09:30", "10:30"))
    assert overlap.status_code == 409
    assert error_of(overlap)["code"] == "timetable_overlap"
    later = created(dept_admin.post(path, slot(1, "10:00", "11:00")))  # back to back is fine
    created(dept_admin.post(path, slot(2, "09:30", "10:30")))  # another day
    # Another section may use the same slot.
    created(
        world.browser("admin").post(
            f"{SECTIONS}/{cse['mech']['id']}/timetable", slot(1, "09:00", "10:00")
        )
    )

    entry = f"{CAMPUS}/timetable-entries/{later['id']}"
    assert dept_admin.patch(entry, {"starts_at": "09:45"}).status_code == 409
    assert dept_admin.patch(entry, {"ends_at": "09:00"}).status_code == 422
    assert dept_admin.post(path, slot(3, "11:00", "10:00")).status_code == 422
    moved = dept_admin.patch(entry, {"weekday": 5, "room": "Lab 3"})
    assert (moved.json()["weekday"], moved.json()["room"]) == (5, "Lab 3")

    listed = world.browser("faculty").get(path).json()["items"]
    assert [(e["weekday"], e["starts_at"]) for e in listed] == [
        (1, "09:00:00"),
        (2, "09:30:00"),
        (5, "10:00:00"),
    ]
    assert dept_admin.send("DELETE", f"{CAMPUS}/timetable-entries/{first['id']}").status_code == 204


def test_timetable_writes_are_for_catalog_managers(world: World, cse: dict[str, Any]) -> None:
    path = f"{SECTIONS}/{cse['section']['id']}/timetable"
    entry = created(world.browser("admin").post(path, slot(1, "09:00", "10:00")))
    for who in ("faculty", "student"):
        browser = world.browser(who)
        assert browser.post(path, slot(2, "09:00", "10:00")).status_code == 403
        assert (
            browser.patch(f"{CAMPUS}/timetable-entries/{entry['id']}", {"room": "x"}).status_code
            == 403
        )
    mech_entry = created(
        world.browser("admin").post(
            f"{SECTIONS}/{cse['mech']['id']}/timetable", slot(1, "09:00", "10:00")
        )
    )
    dept_admin = world.browser("dept_admin")
    assert not_found(
        dept_admin.post(f"{SECTIONS}/{cse['mech']['id']}/timetable", slot(3, "09:00", "10:00"))
    )
    assert not_found(
        dept_admin.patch(f"{CAMPUS}/timetable-entries/{mech_entry['id']}", {"room": "x"})
    )
    assert not_found(dept_admin.send("DELETE", f"{CAMPUS}/timetable-entries/{mech_entry['id']}"))


def test_students_see_only_their_enrolled_sections_in_the_current_term(
    world: World, cse: dict[str, Any]
) -> None:
    """US-13 / ACADEMIC-004."""
    admin = world.browser("admin")
    section_id = cse["section"]["id"]
    import_csv(world, "admin", section_id, "roll_number\nN-001\n")
    import_csv(world, "admin", cse["mech"]["id"], "roll_number\nN-002\n")
    created(admin.post(f"{SECTIONS}/{section_id}/timetable", slot(3, "11:00", "12:00", "B-101")))
    created(admin.post(f"{SECTIONS}/{section_id}/timetable", slot(1, "09:00", "10:00", "B-204")))
    created(
        admin.post(f"{SECTIONS}/{cse['mech']['id']}/timetable", slot(1, "10:00", "11:00", "W-1"))
    )
    # A section the student is enrolled in, in a term that isn't current.
    old = make_term(world, "2025-26 Even", current=False)
    old_section = make_section(world, old, make_subject(world, "CS201"))
    import_csv(world, "admin", old_section["id"], "roll_number\nN-001\n")
    created(admin.post(f"{SECTIONS}/{old_section['id']}/timetable", slot(2, "09:00", "10:00")))

    body = world.browser("student").get(f"{CAMPUS}/me/timetable").json()
    assert body["term"]["id"] == cse["term"]["id"]
    assert body["is_demo"] is False
    assert [
        (c["weekday"], c["starts_at"], c["room"], c["subject"]["code"]) for c in body["classes"]
    ] == [
        (1, "09:00:00", "B-204", "CS301"),
        (3, "11:00:00", "B-101", "CS301"),
    ]
    mech = world.browser("mech_student").get(f"{CAMPUS}/me/timetable").json()
    assert [c["subject"]["code"] for c in mech["classes"]] == ["ME201"]

    for who in ("faculty", "admin", "dept_admin"):
        assert world.browser(who).get(f"{CAMPUS}/me/timetable").status_code == 403


def test_without_a_current_term_the_week_is_empty(world: World) -> None:
    make_term(world, current=False)
    body = world.browser("student").get(f"{CAMPUS}/me/timetable").json()
    assert body == {"term": None, "is_demo": False, "classes": []}
    assert world.browser("faculty").get(f"{CAMPUS}/teaching/sections").json() == {
        "term": None,
        "items": [],
    }
