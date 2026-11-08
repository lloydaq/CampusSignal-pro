"""Tenant isolation suite (TENANT-005): every campus route, called by Northfield's college
admin against Riverside, must deny without leaking. Cases live in tests/tenant_isolation_cases.py.
"""

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CollegeMembership, MembershipKind, MembershipStatus, RoleGrant
from tests.integration.auth_helpers import error_of
from tests.integration.campus_world import World, build_world
from tests.integration.tenancy import make_user
from tests.tenant_isolation_cases import CASES, Kind

pytestmark = pytest.mark.integration

# Anything that would only be in a response if Riverside data leaked.
RIVERSIDE_MARKERS = (
    "riverside",
    "River Admin",
    "River Student",
    "River Applicant",
    "R-001",
    "R-404",
    "RIV101",
    "Hydrology",
)


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    world = build_world(session, app_factory())
    world.river_admin_grant = session.execute(  # type: ignore[attr-defined]
        select(RoleGrant).where(RoleGrant.membership_id == world.members["river_admin"].id)
    ).scalar_one()
    # A pending request at Riverside, from a Riverside applicant.
    applicant = make_user(session, "river_applicant@riverside.example", name="River Applicant")
    world.river_request = CollegeMembership(  # type: ignore[attr-defined]
        user_id=applicant.id,
        college_id=world.river.id,
        kind=MembershipKind.STUDENT,
        status=MembershipStatus.PENDING,
        verification_flag="NO_ROSTER_MATCH",
        submitted_roll_number="R-404",
    )
    session.add(world.river_request)  # type: ignore[attr-defined]
    session.commit()
    # Riverside activity, so its audit log and invites aren't empty.
    river = world.browser("river_admin")
    assert (
        river.post(
            "/api/v1/campus/invites", {"email": "new@riverside.example", "kind": "STAFF"}
        ).status_code
        == 201
    )
    # Riverside notices: one published (with a Riverside-only title), one draft.
    for title, publish in (("Riverside hostel curfew", True), ("Riverside draft plan", False)):
        created = river.post(
            "/api/v1/campus/notices",
            {
                "title": title,
                "body": "Only for Riverside.",
                "category": "GENERAL",
                "scope": "COLLEGE",
                "publish": publish,
            },
        )
        assert created.status_code == 201, created.text
        if publish:
            world.river_notice = created.json()  # type: ignore[attr-defined]
        else:
            world.river_draft = created.json()  # type: ignore[attr-defined]
    # A Riverside issue, reported by its student (a Riverside-only title).
    reported = world.browser("river_student").post(
        "/api/v1/campus/issues",
        {
            "category": "WATER_SANITATION",
            "title": "Riverside hostel taps dry",
            "description": "No water since morning.",
            "location": "Riverside hostel block B",
        },
    )
    assert reported.status_code == 201, reported.text
    world.river_issue = reported.json()  # type: ignore[attr-defined]
    # A Riverside post with a comment (Riverside-only words in both).
    posted = world.browser("river_student").post(
        "/api/v1/campus/posts",
        {"body": "Riverside cricket trials on Sunday", "visibility": "COLLEGE"},
    )
    assert posted.status_code == 201, posted.text
    world.river_post = posted.json()  # type: ignore[attr-defined]
    commented = river.post(
        f"/api/v1/campus/posts/{posted.json()['id']}/comments",
        {"body": "Riverside ground is booked"},
    )
    assert commented.status_code == 201, commented.text
    world.river_comment = commented.json()  # type: ignore[attr-defined]
    # An open Riverside report on that post, so Riverside's queue isn't empty.
    flagged = river.post(
        "/api/v1/campus/reports", {"post_id": posted.json()["id"], "reason": "SPAM"}
    )
    assert flagged.status_code == 201, flagged.text
    world.river_report = flagged.json()  # type: ignore[attr-defined]
    # Riverside academics: a current term, a subject and a section taught by its college admin,
    # its student enrolled, and a timetable entry.
    term = river.post(
        "/api/v1/campus/terms",
        {
            "name": "Riverside monsoon term",
            "starts_on": "2026-07-01",
            "ends_on": "2026-12-01",
            "is_current": True,
        },
    )
    assert term.status_code == 201, term.text
    world.river_term = term.json()  # type: ignore[attr-defined]
    subject = river.post(
        "/api/v1/campus/subjects",
        {
            "department_id": str(world.river.departments["CSE"].id),
            "code": "RIV101",
            "name": "Hydrology",
        },
    )
    assert subject.status_code == 201, subject.text
    world.river_subject = subject.json()  # type: ignore[attr-defined]
    section = river.post(
        "/api/v1/campus/sections",
        {"term_id": term.json()["id"], "subject_id": subject.json()["id"], "name": "Riverside A"},
    )
    assert section.status_code == 201, section.text
    world.river_section = section.json()  # type: ignore[attr-defined]
    section_path = f"/api/v1/campus/sections/{section.json()['id']}"
    taught = river.send(
        "PUT",
        f"{section_path}/instructors",
        {"membership_ids": [str(world.members["river_admin"].id)]},
    )
    assert taught.status_code == 200, taught.text
    enrolled = river.post(f"{section_path}/enrollments/import", {"csv": "roll_number\nR-001\n"})
    assert enrolled.status_code == 201, enrolled.text
    enrollments = river.get(f"{section_path}/enrollments").json()["items"]
    world.river_enrollment = enrollments[0]  # type: ignore[attr-defined]
    entry = river.post(
        f"{section_path}/timetable",
        {"weekday": 1, "starts_at": "09:00", "ends_at": "10:00", "room": "Riverside hall"},
    )
    assert entry.status_code == 201, entry.text
    world.river_entry = entry.json()  # type: ignore[attr-defined]
    recorded = river.post(
        f"{section_path}/attendance-sessions",
        {
            "held_on": "2026-10-20",
            "slot": 1,
            "records": [{"enrollment_id": enrollments[0]["id"], "status": "PRESENT"}],
        },
    )
    assert recorded.status_code == 201, recorded.text
    world.river_session = recorded.json()  # type: ignore[attr-defined]
    # A published Riverside assessment with its student's score.
    assessment = river.post(
        f"{section_path}/assessments",
        {"name": "Riverside quiz", "kind": "QUIZ", "max_score": "10", "held_on": "2026-10-20"},
    )
    assert assessment.status_code == 201, assessment.text
    scored = river.send(
        "PUT",
        f"/api/v1/campus/assessments/{assessment.json()['id']}/results",
        {
            "version": 1,
            "results": [{"enrollment_id": enrollments[0]["id"], "score": "7", "absent": False}],
        },
    )
    assert scored.status_code == 200, scored.text
    published = river.post(
        f"/api/v1/campus/assessments/{assessment.json()['id']}/publish", {"version": 2}
    )
    assert published.status_code == 200, published.text
    world.river_assessment = published.json()  # type: ignore[attr-defined]
    return world


def assert_no_riverside_data(text: str) -> None:
    lowered = text.lower()
    for marker in RIVERSIDE_MARKERS:
        assert marker.lower() not in lowered, marker


OPERATIONS = sorted(CASES)


@pytest.mark.parametrize("operation", OPERATIONS, ids=[" ".join(op) for op in OPERATIONS])
def test_northfield_admin_cannot_reach_riverside(world: World, operation: tuple[str, str]) -> None:
    method, _ = operation
    case = CASES[operation]
    path, body = case.request(world)
    response = world.browser(case.who).send(method, path, body)

    if case.kind == Kind.OBJECT:
        assert response.status_code == 404, response.text
        assert error_of(response) == {
            "code": "not_found",
            "message": "Not found.",
            "details": None,
            "request_id": error_of(response)["request_id"],
        }
    elif case.kind == Kind.LIST:
        assert response.status_code == 200, response.text
    else:
        assert response.status_code == 422, response.text
        assert any(d["field"] == "college_id" for d in error_of(response)["details"])
    assert_no_riverside_data(response.text)
