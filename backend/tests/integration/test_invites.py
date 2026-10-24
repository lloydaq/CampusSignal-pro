"""First college admin invites (ADMIN-002) and invite acceptance (MEMBER-007, P-7, US-11).

Accepting requires being signed in as the invited address; it marks that email verified and
ends the account's other sessions (decided 2026-10-23, pre-hijacking defence)."""

import re
from collections.abc import Callable

import pytest
from fastapi import FastAPI
from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.core.mailer import InMemoryMailer
from app.models import CollegeStatus, MembershipKind, MembershipStatus, Role
from tests.integration.auth_helpers import PREFIX, error_of, scalar
from tests.integration.platform_helpers import PLATFORM, Browser
from tests.integration.tenancy import Campus, add_member, make_college, make_user, two_colleges

pytestmark = pytest.mark.integration

OPS = "ops@campussignal.example"
INVITEE = "principal@northfield.example"
ACCEPT = "/api/v1/invites/accept"
TOKEN_RE = re.compile(r"/invites/accept#token=([A-Za-z0-9_-]+)")


@pytest.fixture
def app(app_factory: Callable[..., FastAPI]) -> FastAPI:
    return app_factory()


@pytest.fixture
def mailer(app: FastAPI) -> InMemoryMailer:
    m = app.state.mailer
    assert isinstance(m, InMemoryMailer)
    return m


@pytest.fixture
def north(session: Session) -> Campus:
    campus, _ = two_colleges(session)
    campus.college.status = CollegeStatus.ONBOARDING
    make_user(session, OPS, platform_admin=True)
    session.commit()
    return campus


@pytest.fixture
def ops(app: FastAPI, north: Campus) -> Browser:
    return Browser(app, OPS)


def invite(
    ops: Browser, north: Campus, mailer: InMemoryMailer, email: str = INVITEE, **extra: str
) -> str:
    mailer.outbox.clear()
    response = ops.post(
        f"{PLATFORM}/colleges/{north.id}/admin-invites",
        {"email": email, "kind": "FACULTY", **extra},
    )
    assert response.status_code == 201, response.text
    mail = next(m for m in mailer.outbox if m.to == email)
    match = TOKEN_RE.search(mail.text)
    assert match
    return match.group(1)


def test_the_invited_admin_joins_as_active_faculty_with_college_admin(
    session: Session,
    app: FastAPI,
    ops: Browser,
    north: Campus,
    mailer: InMemoryMailer,
    conn: Connection,
) -> None:
    token = invite(ops, north, mailer)
    assert "Northfield Institute" in mailer.outbox[0].subject
    make_user(session, INVITEE, verified=False)
    session.commit()
    other_browser = Browser(app, INVITEE)
    browser = Browser(app, INVITEE)

    response = browser.post(ACCEPT, {"token": token})
    assert response.status_code == 200
    assert response.json()["membership"]["college"]["slug"] == "northfield"

    me = browser.get(f"{PREFIX}/me").json()
    assert me["user"]["email_verified"] is True
    assert me["membership"]["kind"] == "FACULTY"
    assert me["membership"]["status"] == "ACTIVE"
    assert me["roles"] == [{"role": "COLLEGE_ADMIN", "department": None}]
    assert other_browser.get(f"{PREFIX}/me").status_code == 401  # other sessions ended
    assert (
        scalar(
            conn,
            "SELECT count(*) FROM audit_log "
            "WHERE action = 'membership.invite_accepted' AND college_id = :c",
            c=north.id,
        )
        == 1
    )
    assert (
        scalar(conn, "SELECT count(*) FROM audit_log WHERE action = 'platform.admin_invited'") == 1
    )

    again = browser.post(ACCEPT, {"token": token})
    assert again.status_code == 400
    assert error_of(again)["code"] == "token_used"


def test_the_invite_is_bound_to_its_email(
    session: Session, app: FastAPI, ops: Browser, north: Campus, mailer: InMemoryMailer
) -> None:
    token = invite(ops, north, mailer)
    make_user(session, "someone.else@northfield.example")
    session.commit()
    response = Browser(app, "someone.else@northfield.example").post(ACCEPT, {"token": token})
    assert response.status_code == 403
    assert error_of(response)["code"] == "invite_email_mismatch"
    assert INVITEE not in response.text

    make_user(session, INVITEE)
    session.commit()
    assert Browser(app, INVITEE).post(ACCEPT, {"token": token}).status_code == 200  # still usable


def test_a_platform_admin_can_never_accept(
    session: Session, app: FastAPI, ops: Browser, north: Campus, mailer: InMemoryMailer
) -> None:
    token = invite(ops, north, mailer, email="x@northfield.example")
    make_user(session, "second-ops@northfield.example", platform_admin=True)
    session.commit()
    # Even when the invite names the platform admin's own address (set up directly here).
    session.execute(text("UPDATE invites SET email = 'second-ops@northfield.example'"))
    session.commit()
    response = Browser(app, "second-ops@northfield.example").post(ACCEPT, {"token": token})
    assert response.status_code == 403  # US-11, P-7
    assert error_of(response)["code"] == "platform_admin_cannot_join"


def test_inviting_a_platform_admin_address_is_refused(
    session: Session, ops: Browser, north: Campus
) -> None:
    response = ops.post(
        f"{PLATFORM}/colleges/{north.id}/admin-invites", {"email": OPS, "kind": "STAFF"}
    )
    assert response.status_code == 422
    assert error_of(response)["details"][0]["field"] == "email"


@pytest.mark.parametrize(
    ("change", "code"),
    [("expired", "token_expired"), ("garbage", "token_invalid"), ("revoked", "token_invalid")],
)
def test_bad_tokens(
    session: Session,
    app: FastAPI,
    ops: Browser,
    north: Campus,
    mailer: InMemoryMailer,
    clock: object,
    change: str,
    code: str,
) -> None:
    token = invite(ops, north, mailer)
    make_user(session, INVITEE)
    session.commit()
    if change == "expired":
        clock.advance(days=7, seconds=1)  # type: ignore[attr-defined]
    elif change == "garbage":
        token = "x" * 43
    else:
        invite(ops, north, mailer)  # a newer invite to the same address revokes the older one
    response = Browser(app, INVITEE).post(ACCEPT, {"token": token})
    assert response.status_code == 400
    assert error_of(response)["code"] == code


def test_an_active_member_of_another_college_cannot_accept(
    session: Session, app: FastAPI, ops: Browser, north: Campus, mailer: InMemoryMailer
) -> None:
    token = invite(ops, north, mailer)
    hill = make_college(session, "Hill College", "hill")
    add_member(session, make_user(session, INVITEE), hill)
    session.commit()
    response = Browser(app, INVITEE).post(ACCEPT, {"token": token})
    assert response.status_code == 409
    assert error_of(response)["code"] == "already_member"


def test_an_existing_member_of_the_same_college_gains_the_role(
    session: Session, app: FastAPI, ops: Browser, north: Campus, mailer: InMemoryMailer
) -> None:
    membership = add_member(session, make_user(session, INVITEE), north, MembershipKind.STAFF)
    session.commit()
    token = invite(ops, north, mailer)
    assert Browser(app, INVITEE).post(ACCEPT, {"token": token}).status_code == 200
    me = Browser(app, INVITEE).get(f"{PREFIX}/me").json()
    assert me["membership"]["id"] == str(membership.id)
    assert me["membership"]["kind"] == "STAFF"
    assert me["roles"] == [{"role": "COLLEGE_ADMIN", "department": None}]


def test_a_suspended_college_refuses_acceptance(
    session: Session, app: FastAPI, ops: Browser, north: Campus, mailer: InMemoryMailer
) -> None:
    token = invite(ops, north, mailer)
    north.college.status = CollegeStatus.SUSPENDED
    make_user(session, INVITEE)
    session.commit()
    response = Browser(app, INVITEE).post(ACCEPT, {"token": token})
    assert response.status_code == 403
    assert error_of(response)["code"] == "college_inactive"


def test_accepting_needs_a_session(
    app: FastAPI, ops: Browser, north: Campus, mailer: InMemoryMailer
) -> None:
    token = invite(ops, north, mailer)
    assert Browser(app).post(ACCEPT, {"token": token}).status_code == 401


def test_a_second_admin_invite_needs_a_reason_and_tells_the_current_admins(
    session: Session,
    app: FastAPI,
    ops: Browser,
    north: Campus,
    mailer: InMemoryMailer,
    conn: Connection,
) -> None:
    add_member(
        session,
        make_user(session, "admin@northfield.example"),
        north,
        MembershipKind.FACULTY,
        roles=((Role.COLLEGE_ADMIN, None),),
    )
    add_member(
        session,
        make_user(session, "former@northfield.example"),
        north,
        MembershipKind.FACULTY,
        status=MembershipStatus.ENDED,
        roles=((Role.COLLEGE_ADMIN, None),),
    )
    session.commit()

    response = ops.post(
        f"{PLATFORM}/colleges/{north.id}/admin-invites", {"email": INVITEE, "kind": "FACULTY"}
    )
    assert response.status_code == 422
    assert error_of(response)["details"][0]["field"] == "reason"

    invite(ops, north, mailer, reason="Principal changed")
    recipients = sorted(m.to for m in mailer.outbox)
    assert recipients == ["admin@northfield.example", INVITEE]  # not the former admin
    notice = next(m for m in mailer.outbox if m.to == "admin@northfield.example")
    assert "Principal changed" in notice.text
    assert "#token=" not in notice.text
    assert (
        scalar(conn, "SELECT reason FROM audit_log WHERE action = 'platform.admin_invited'")
        == "Principal changed"
    )


def test_invites_expire_after_seven_days(
    session: Session,
    app: FastAPI,
    ops: Browser,
    north: Campus,
    mailer: InMemoryMailer,
    clock: object,
) -> None:
    token = invite(ops, north, mailer)
    make_user(session, INVITEE)
    session.commit()
    clock.advance(days=6, hours=23)  # type: ignore[attr-defined]
    assert Browser(app, INVITEE).post(ACCEPT, {"token": token}).status_code == 200


def test_the_college_detail_lists_its_admin_invites(
    app: FastAPI, ops: Browser, north: Campus, mailer: InMemoryMailer, clock: object
) -> None:
    invite(ops, north, mailer)
    invite(ops, north, mailer, email="deputy@northfield.example")
    invites = ops.get(f"{PLATFORM}/colleges/{north.id}").json()["admin_invites"]
    assert sorted((i["email"], i["state"]) for i in invites) == [
        ("deputy@northfield.example", "PENDING"),
        (INVITEE, "PENDING"),
    ]
    clock.advance(days=8)  # type: ignore[attr-defined]
    ops = Browser(app, OPS)  # the old platform session idled out (24 h, P-10)
    detail = ops.get(f"{PLATFORM}/colleges/{north.id}").json()
    assert {i["state"] for i in detail["admin_invites"]} == {"EXPIRED"}
