"""Platform admins onboard colleges (ADMIN-001, US-11) and nobody else can even see the
platform routes (architecture.md §7: 404, route existence not revealed)."""

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from app.models import CollegeStatus, MembershipKind, Role
from tests.integration.auth_helpers import PREFIX, error_of, scalar
from tests.integration.platform_helpers import PLATFORM, Browser
from tests.integration.tenancy import add_member, make_user, two_colleges

pytestmark = pytest.mark.integration

OPS = "ops@campussignal.example"
NEW_COLLEGE = {"name": "Hillcrest University", "slug": "hillcrest", "timezone": "Asia/Kolkata"}


@pytest.fixture
def app(app_factory: Callable[..., FastAPI]) -> FastAPI:
    return app_factory()


@pytest.fixture
def ops(session: Session, app: FastAPI) -> Browser:
    make_user(session, OPS, platform_admin=True)
    session.commit()
    return Browser(app, OPS)


def test_a_platform_admin_creates_a_college_in_onboarding(ops: Browser, conn: Connection) -> None:
    response = ops.post(
        f"{PLATFORM}/colleges", {**NEW_COLLEGE, "email_domains": ["Hillcrest.EDU"], "is_demo": True}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ONBOARDING"
    assert body["email_domains"] == ["hillcrest.edu"]
    assert body["is_demo"] is True
    assert (
        scalar(
            conn,
            "SELECT count(*) FROM audit_log "
            "WHERE action = 'platform.college_created' AND college_id = :id",
            id=body["id"],
        )
        == 1
    )


def test_an_existing_slug_is_409(ops: Browser) -> None:
    assert ops.post(f"{PLATFORM}/colleges", NEW_COLLEGE).status_code == 201
    response = ops.post(f"{PLATFORM}/colleges", {**NEW_COLLEGE, "name": "Other"})
    assert response.status_code == 409  # US-11
    assert error_of(response)["code"] == "slug_taken"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("slug", "Hill Crest"),
        ("slug", "-x"),
        ("timezone", "Mars/Olympus"),
        ("timezone", "localtime"),
        ("name", ""),
    ],
)
def test_invalid_college_fields_are_422(ops: Browser, field: str, value: str) -> None:
    response = ops.post(f"{PLATFORM}/colleges", {**NEW_COLLEGE, field: value})
    assert response.status_code == 422
    assert error_of(response)["details"][0]["field"] == field


def test_unknown_fields_are_refused(ops: Browser) -> None:
    assert ops.post(f"{PLATFORM}/colleges", {**NEW_COLLEGE, "status": "ACTIVE"}).status_code == 422


def test_colleges_are_listed_newest_first_with_a_cursor(ops: Browser, clock: object) -> None:
    for i in range(3):
        assert (
            ops.post(
                f"{PLATFORM}/colleges",
                {**NEW_COLLEGE, "slug": f"college-{i}", "name": f"College {i}"},
            ).status_code
            == 201
        )
        clock.advance(minutes=1)  # type: ignore[attr-defined]
    first = ops.get(f"{PLATFORM}/colleges", limit=2).json()
    assert [c["slug"] for c in first["items"]] == ["college-2", "college-1"]
    second = ops.get(f"{PLATFORM}/colleges", limit=2, cursor=first["next_cursor"]).json()
    assert [c["slug"] for c in second["items"]] == ["college-0"]
    assert second["next_cursor"] is None
    assert ops.get(f"{PLATFORM}/colleges", cursor="not-a-cursor").status_code == 422


def test_lifecycle_onboarding_active_suspended_active(ops: Browser, conn: Connection) -> None:
    college_id = ops.post(f"{PLATFORM}/colleges", NEW_COLLEGE).json()["id"]
    path = f"{PLATFORM}/colleges/{college_id}"
    assert ops.patch(path, {"status": "ACTIVE"}).json()["status"] == "ACTIVE"

    missing_reason = ops.patch(path, {"status": "SUSPENDED"})
    assert missing_reason.status_code == 422
    assert error_of(missing_reason)["details"][0]["field"] == "reason"
    assert (
        ops.patch(path, {"status": "SUSPENDED", "reason": "Contract paused"}).json()["status"]
        == "SUSPENDED"
    )
    assert ops.patch(path, {"status": "ACTIVE"}).json()["status"] == "ACTIVE"

    back = ops.patch(path, {"status": "ONBOARDING"})
    assert back.status_code == 409
    assert error_of(back)["code"] == "invalid_transition"
    reasons = scalar(
        conn,
        "SELECT array_agg(reason ORDER BY created_at) FROM audit_log "
        "WHERE action = 'platform.college_status_changed'",
    )
    assert reasons == [None, "Contract paused", None]


def test_editing_details_keeps_the_slug(ops: Browser) -> None:
    college_id = ops.post(f"{PLATFORM}/colleges", NEW_COLLEGE).json()["id"]
    body = ops.patch(
        f"{PLATFORM}/colleges/{college_id}", {"name": "Hillcrest Univ.", "timezone": "UTC"}
    ).json()
    assert (body["name"], body["timezone"], body["slug"]) == ("Hillcrest Univ.", "UTC", "hillcrest")
    assert ops.patch(f"{PLATFORM}/colleges/{college_id}", {"slug": "other"}).status_code == 422


def test_suspending_a_college_cuts_its_members_off(
    session: Session, app: FastAPI, ops: Browser
) -> None:
    north, _ = two_colleges(session)
    add_member(session, make_user(session, "s@northfield.example"), north)
    session.commit()
    student = Browser(app, "s@northfield.example")
    assert student.get(f"{PREFIX}/me").json()["capabilities"] == ["campus"]

    assert (
        ops.patch(
            f"{PLATFORM}/colleges/{north.id}", {"status": "SUSPENDED", "reason": "Unpaid"}
        ).status_code
        == 200
    )
    me = student.get(f"{PREFIX}/me").json()
    assert me["capabilities"] == []
    assert me["membership"]["college"]["status"] == "SUSPENDED"


def test_an_unknown_college_is_404(ops: Browser) -> None:
    assert ops.get(f"{PLATFORM}/colleges/00000000-0000-0000-0000-000000000000").status_code == 404


def test_the_college_detail_shows_metadata_only(session: Session, ops: Browser) -> None:
    north, _ = two_colleges(session)
    add_member(session, make_user(session, "s@northfield.example", name="Secret Student"), north)
    session.commit()
    body = ops.get(f"{PLATFORM}/colleges/{north.id}").json()
    assert body["active_member_count"] == 1
    # ADMIN-008: no member names, emails, departments' content or roster data.
    for leaked in ("Secret Student", "s@northfield.example", "roster"):
        assert leaked not in str(body)


# --- nobody else sees the platform ---------------------------------------------------------

PLATFORM_CALLS = [
    ("GET", "/colleges", None),
    ("POST", "/colleges", NEW_COLLEGE),
    ("GET", "/colleges/{id}", None),
    ("PATCH", "/colleges/{id}", {"status": "SUSPENDED", "reason": "x"}),
    ("POST", "/colleges/{id}/admin-invites", {"email": "x@hillcrest.example", "kind": "FACULTY"}),
    ("GET", "/users", None),
    ("POST", "/users/{id}/suspend", {"reason": "x"}),
    ("POST", "/users/{id}/unsuspend", {}),
    ("GET", "/audit-log", None),
]


@pytest.mark.parametrize("who", ["student", "college_admin", "no_membership"])
@pytest.mark.parametrize(("method", "path", "body"), PLATFORM_CALLS)
def test_everyone_but_platform_admins_gets_404(
    session: Session, app: FastAPI, who: str, method: str, path: str, body: dict[str, str] | None
) -> None:
    north, _ = two_colleges(session)
    user = make_user(session, f"{who}@northfield.example")
    if who == "student":
        add_member(session, user, north)
    elif who == "college_admin":
        add_member(
            session, user, north, MembershipKind.FACULTY, roles=((Role.COLLEGE_ADMIN, None),)
        )
    session.commit()

    response = Browser(app, user.email).send(
        method, PLATFORM + path.format(id=north.id if "colleges" in path else user.id), body
    )
    assert response.status_code == 404
    assert error_of(response)["code"] == "not_found"
    assert "Northfield" not in response.text
    session.refresh(north.college)
    assert north.college.status == CollegeStatus.ACTIVE  # nothing changed


def test_signed_out_platform_calls_are_401(app: FastAPI) -> None:
    assert Browser(app).get(f"{PLATFORM}/colleges").status_code == 401
