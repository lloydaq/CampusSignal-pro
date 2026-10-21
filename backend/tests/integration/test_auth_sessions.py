"""Sessions, CSRF, sign-out and password change (PRD AUTH-005/008/010, architecture.md §10)."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.core.mailer import InMemoryMailer
from tests.integration.auth_helpers import (
    NEW_PASSWORD,
    PASSWORD,
    PREFIX,
    create_user,
    csrf,
    error_of,
    login,
    scalar,
    signed_in,
    sql,
)

pytestmark = pytest.mark.integration

WRONG = "not-the-right-password"


@pytest.fixture
def user(api: TestClient, mailer: InMemoryMailer) -> None:
    create_user(api, mailer)
    api.cookies.clear()


def _change(api: TestClient, current: str = PASSWORD, new: str = NEW_PASSWORD) -> Any:
    return api.post(
        f"{PREFIX}/me/password",
        json={"current_password": current, "new_password": new},
        headers=csrf(api),
    )


# --- session lifetime --------------------------------------------------------------------


def test_requests_without_a_session_are_401(api: TestClient, user: None) -> None:
    response = api.get(f"{PREFIX}/me")
    assert response.status_code == 401
    assert error_of(response)["code"] == "not_authenticated"


def test_an_unknown_or_malformed_cookie_is_401(api: TestClient, user: None) -> None:
    api.cookies.set("cs_session", "forged-value", domain="testserver.local")
    assert api.get(f"{PREFIX}/me").status_code == 401


def test_an_idle_session_ends_after_seven_days(
    api: TestClient, user: None, clock: Any, conn: Connection
) -> None:
    login(api)
    clock.advance(days=6, hours=23)
    assert api.get(f"{PREFIX}/me").status_code == 200  # activity renews the idle window
    clock.advance(days=6, hours=23)
    assert api.get(f"{PREFIX}/me").status_code == 200
    clock.advance(days=7)
    assert api.get(f"{PREFIX}/me").status_code == 401
    assert scalar(conn, "SELECT count(*) FROM sessions") == 0


def test_a_session_ends_thirty_days_after_sign_in_however_active(
    api: TestClient, user: None, clock: Any
) -> None:
    login(api)
    for _ in range(4):
        clock.advance(days=6)
        assert api.get(f"{PREFIX}/me").status_code == 200
    clock.advance(days=6)  # day 30
    assert api.get(f"{PREFIX}/me").status_code == 401


def test_platform_admin_sessions_idle_out_after_a_day_and_end_after_a_week(
    api: TestClient, user: None, conn: Connection, clock: Any
) -> None:
    sql(conn, "UPDATE users SET platform_role = 'PLATFORM_ADMIN'")
    login(api)
    clock.advance(hours=23)
    assert api.get(f"{PREFIX}/me").status_code == 200
    clock.advance(hours=25)
    assert api.get(f"{PREFIX}/me").status_code == 401

    login(api)
    for _ in range(6):
        clock.advance(hours=23)
        assert api.get(f"{PREFIX}/me").status_code == 200
    clock.advance(days=1)
    assert api.get(f"{PREFIX}/me").status_code == 401


def test_last_seen_is_updated_at_most_every_five_minutes(
    api: TestClient, user: None, clock: Any, conn: Connection
) -> None:
    login(api)
    started = scalar(conn, "SELECT last_seen_at FROM sessions")
    clock.advance(minutes=4)
    api.get(f"{PREFIX}/me")
    assert scalar(conn, "SELECT last_seen_at FROM sessions") == started
    clock.advance(minutes=1)
    api.get(f"{PREFIX}/me")
    assert scalar(conn, "SELECT last_seen_at FROM sessions") == clock.now


# --- CSRF and Origin ---------------------------------------------------------------------


def test_the_csrf_endpoint_returns_the_token_that_login_gave(api: TestClient, user: None) -> None:
    token = login(api).json()["csrf_token"]
    response = api.get(f"{PREFIX}/auth/csrf")
    assert response.json() == {"csrf_token": token}
    assert response.headers["Cache-Control"] == "no-store"


def test_the_csrf_endpoint_says_null_when_signed_out(api: TestClient, user: None) -> None:
    response = api.get(f"{PREFIX}/auth/csrf")
    assert response.status_code == 200
    assert response.json() == {"csrf_token": None}


@pytest.mark.parametrize(
    "path", ["/auth/logout", "/auth/logout-all", "/auth/resend-verification", "/me/password"]
)
def test_signed_in_writes_need_the_csrf_header(api: TestClient, user: None, path: str) -> None:
    login(api)
    body = {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    missing = api.post(f"{PREFIX}{path}", json=body)
    wrong = api.post(f"{PREFIX}{path}", json=body, headers={"X-CSRF-Token": "x" * 43})
    for response in (missing, wrong):
        assert response.status_code == 403
        assert error_of(response)["code"] == "csrf_failed"
    assert api.get(f"{PREFIX}/me").status_code == 200  # nothing happened


def test_a_token_from_another_session_does_not_work(
    api: TestClient, auth_app: FastAPI, mailer: InMemoryMailer, user: None
) -> None:
    login(api)
    other = signed_in(auth_app, mailer)
    response = api.post(f"{PREFIX}/auth/logout", headers=csrf(other))
    assert response.status_code == 403


def test_the_csrf_cookie_alone_is_not_enough_without_the_header(
    api: TestClient, user: None
) -> None:
    login(api)
    assert api.cookies.get("cs_csrf")
    assert api.post(f"{PREFIX}/auth/logout").status_code == 403


def test_a_wrong_origin_is_refused_even_with_valid_cookie_and_token(
    api: TestClient, user: None
) -> None:
    login(api)
    response = api.post(
        f"{PREFIX}/auth/logout", headers={**csrf(api), "Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert error_of(response)["code"] == "origin_not_allowed"
    assert api.get(f"{PREFIX}/me").status_code == 200


def test_reads_do_not_need_csrf(api: TestClient, user: None) -> None:
    login(api)
    assert api.get(f"{PREFIX}/me").status_code == 200


# --- sign-out ----------------------------------------------------------------------------


def test_logout_deletes_the_session_and_clears_both_cookies(
    api: TestClient, user: None, conn: Connection
) -> None:
    login(api)
    response = api.post(f"{PREFIX}/auth/logout", headers=csrf(api))
    assert response.status_code == 204
    cleared = " ".join(response.headers.get_list("set-cookie")).lower()
    assert "cs_session=" in cleared and "cs_csrf=" in cleared and "max-age=0" in cleared
    assert scalar(conn, "SELECT count(*) FROM sessions") == 0
    assert api.get(f"{PREFIX}/me").status_code == 401


def test_a_stolen_cookie_is_dead_after_logout(
    api: TestClient, auth_app: FastAPI, user: None
) -> None:
    login(api)
    stolen = api.cookies.get("cs_session")
    api.post(f"{PREFIX}/auth/logout", headers=csrf(api))
    thief = TestClient(auth_app, raise_server_exceptions=False)
    thief.cookies.set("cs_session", stolen or "", domain="testserver.local")
    assert thief.get(f"{PREFIX}/me").status_code == 401


def test_logout_all_ends_every_browser(
    api: TestClient, auth_app: FastAPI, mailer: InMemoryMailer, user: None, conn: Connection
) -> None:
    login(api)
    phone = signed_in(auth_app, mailer)
    assert scalar(conn, "SELECT count(*) FROM sessions") == 2
    assert api.post(f"{PREFIX}/auth/logout-all", headers=csrf(api)).status_code == 204
    assert scalar(conn, "SELECT count(*) FROM sessions") == 0
    assert phone.get(f"{PREFIX}/me").status_code == 401
    assert api.get(f"{PREFIX}/me").status_code == 401


def test_logout_only_ends_this_browser(
    api: TestClient, auth_app: FastAPI, mailer: InMemoryMailer, user: None
) -> None:
    login(api)
    phone = signed_in(auth_app, mailer)
    api.post(f"{PREFIX}/auth/logout", headers=csrf(api))
    assert phone.get(f"{PREFIX}/me").status_code == 200


# --- change password (AUTH-010) ----------------------------------------------------------


def test_changing_the_password_rotates_the_session_and_ends_the_others(
    api: TestClient, auth_app: FastAPI, mailer: InMemoryMailer, user: None, conn: Connection
) -> None:
    login(api)
    phone = signed_in(auth_app, mailer)
    old_cookie, old_csrf = api.cookies.get("cs_session"), api.cookies.get("cs_csrf")

    response = _change(api)
    assert response.status_code == 200
    assert set(response.json()) == {"csrf_token"}
    assert api.cookies.get("cs_session") != old_cookie
    assert api.cookies.get("cs_csrf") == response.json()["csrf_token"] != old_csrf
    assert scalar(conn, "SELECT count(*) FROM sessions") == 1
    assert api.get(f"{PREFIX}/me").status_code == 200  # this browser stays signed in
    assert phone.get(f"{PREFIX}/me").status_code == 401

    api.cookies.clear()
    assert login(api, password=PASSWORD).status_code == 401
    assert login(api, password=NEW_PASSWORD).status_code == 200


def test_changing_the_password_is_audited_without_secrets(
    api: TestClient, user: None, conn: Connection
) -> None:
    login(api)
    _change(api)
    row = sql(
        conn,
        "SELECT target_type, actor_user_id::text, metadata::text FROM audit_log "
        "WHERE action = 'auth.password_changed'",
    ).one()
    assert row[0] == "user"
    assert row[1] == str(scalar(conn, "SELECT id FROM users"))
    assert PASSWORD not in row[2]
    assert NEW_PASSWORD not in row[2]


def test_a_wrong_current_password_is_rejected_and_changes_nothing(
    api: TestClient, user: None, conn: Connection
) -> None:
    login(api)
    before = scalar(conn, "SELECT password_hash FROM users")
    response = _change(api, current=WRONG)
    assert response.status_code == 400
    assert error_of(response)["code"] == "wrong_password"
    assert error_of(response)["details"][0]["field"] == "current_password"
    assert scalar(conn, "SELECT password_hash FROM users") == before
    assert api.get(f"{PREFIX}/me").status_code == 200


def test_five_wrong_current_passwords_lock_the_form_even_for_the_right_one(
    api: TestClient, user: None
) -> None:
    login(api)
    assert [_change(api, current=WRONG).status_code for _ in range(5)] == [400] * 5
    locked = _change(api)
    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) > 0


def test_the_lock_ends_with_the_window(api: TestClient, user: None, clock: Any) -> None:
    login(api)
    for _ in range(5):
        _change(api, current=WRONG)
    assert _change(api).status_code == 429
    clock.advance(minutes=15)
    assert _change(api).status_code == 200


def test_a_successful_change_clears_the_failure_count(api: TestClient, user: None) -> None:
    login(api)
    for _ in range(4):
        _change(api, current=WRONG)
    assert _change(api).status_code == 200
    statuses = [_change(api, current=WRONG).status_code for _ in range(4)]
    assert statuses == [400] * 4  # the earlier four no longer count


def test_a_weak_new_password_is_a_field_error_and_keeps_the_password(
    api: TestClient, user: None, conn: Connection
) -> None:
    login(api)
    before = scalar(conn, "SELECT password_hash FROM users")
    response = _change(api, new="password1234")
    assert response.status_code == 422
    assert error_of(response)["details"][0]["field"] == "new_password"
    assert scalar(conn, "SELECT password_hash FROM users") == before
    assert scalar(conn, "SELECT count(*) FROM sessions") == 1


def test_the_old_session_cookie_cannot_be_used_after_a_password_change(
    api: TestClient, auth_app: FastAPI, user: None
) -> None:
    login(api)
    old = api.cookies.get("cs_session")
    _change(api)
    thief = TestClient(auth_app, raise_server_exceptions=False)
    thief.cookies.set("cs_session", old or "", domain="testserver.local")
    assert thief.get(f"{PREFIX}/me").status_code == 401
