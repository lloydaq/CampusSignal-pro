"""Platform user suspension (ADMIN-004, AUTH-009) and the platform audit log (ADMIN-007)."""

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from tests.integration.auth_helpers import PREFIX, error_of, login, scalar
from tests.integration.platform_helpers import PLATFORM, Browser
from tests.integration.tenancy import PASSWORD, add_member, make_user, two_colleges

pytestmark = pytest.mark.integration

OPS = "ops@campussignal.example"
TARGET = "aarav@northfield.example"


@pytest.fixture
def app(app_factory: Callable[..., FastAPI]) -> FastAPI:
    return app_factory()


@pytest.fixture
def ops(session: Session, app: FastAPI) -> Browser:
    make_user(session, OPS, platform_admin=True)
    north, _ = two_colleges(session)
    add_member(session, make_user(session, TARGET, name="Aarav Nair"), north)
    session.commit()
    return Browser(app, OPS)


def target_id(ops: Browser) -> str:
    found = ops.get(f"{PLATFORM}/users", email=TARGET.upper()).json()["items"]
    assert len(found) == 1
    user_id: str = found[0]["id"]
    return user_id


def test_find_a_user_by_exact_email(ops: Browser) -> None:
    found = ops.get(f"{PLATFORM}/users", email=TARGET).json()["items"]
    assert found == [
        {
            "id": found[0]["id"],
            "email": TARGET,
            "display_name": "Aarav Nair",
            "status": "ACTIVE",
            "platform_role": None,
        }
    ]
    assert ops.get(f"{PLATFORM}/users", email="aarav@north.example").json()["items"] == []
    assert ops.get(f"{PLATFORM}/users", email="aarav@").status_code == 422  # no partial search
    assert ops.get(f"{PLATFORM}/users").status_code == 422


def test_suspending_ends_sessions_and_blocks_sign_in(
    ops: Browser, app: FastAPI, conn: Connection
) -> None:
    victim = Browser(app, TARGET)
    user_id = target_id(ops)

    missing = ops.post(f"{PLATFORM}/users/{user_id}/suspend", {})
    assert missing.status_code == 422
    response = ops.post(f"{PLATFORM}/users/{user_id}/suspend", {"reason": "Abuse report"})
    assert response.status_code == 200
    assert response.json()["status"] == "SUSPENDED"

    assert victim.get(f"{PREFIX}/me").status_code == 401
    assert login(Browser(app).client, TARGET, PASSWORD).status_code == 401
    assert (
        scalar(conn, "SELECT reason FROM audit_log WHERE action = 'platform.user_suspended'")
        == "Abuse report"
    )

    assert ops.post(f"{PLATFORM}/users/{user_id}/suspend", {"reason": "again"}).status_code == 409
    assert ops.post(f"{PLATFORM}/users/{user_id}/unsuspend", {}).json()["status"] == "ACTIVE"
    assert login(Browser(app).client, TARGET, PASSWORD).status_code == 200
    assert ops.post(f"{PLATFORM}/users/{user_id}/unsuspend", {}).status_code == 409


def test_a_platform_admin_cannot_suspend_themselves(ops: Browser) -> None:
    me = ops.get(f"{PREFIX}/me").json()["user"]["id"]
    response = ops.post(f"{PLATFORM}/users/{me}/suspend", {"reason": "oops"})
    assert response.status_code == 409
    assert error_of(response)["code"] == "cannot_suspend_self"


def test_an_unknown_user_is_404(ops: Browser) -> None:
    assert (
        ops.post(
            f"{PLATFORM}/users/00000000-0000-0000-0000-000000000000/suspend", {"reason": "x"}
        ).status_code
        == 404
    )


def test_the_platform_audit_log_lists_platform_entries_newest_first(
    ops: Browser, clock: object, conn: Connection
) -> None:
    user_id = target_id(ops)
    ops.post(f"{PLATFORM}/users/{user_id}/suspend", {"reason": "Abuse report"})
    clock.advance(minutes=1)  # type: ignore[attr-defined]
    ops.post(f"{PLATFORM}/users/{user_id}/unsuspend", {})
    conn.exec_driver_sql("INSERT INTO audit_log (action) VALUES ('auth.password_changed')")

    page = ops.get(f"{PLATFORM}/audit-log", limit=10).json()
    assert [e["action"] for e in page["items"]] == [
        "platform.user_unsuspended",
        "platform.user_suspended",
    ]
    entry = page["items"][1]
    assert entry["reason"] == "Abuse report"
    assert entry["target_type"] == "user"
    assert TARGET not in str(page)  # entries name accounts by id only
