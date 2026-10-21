"""Sign-in (PRD AUTH-004/007/009): cookies, generic failures, lockouts, audit, rotation."""

import hashlib
from typing import Any

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.core import security
from app.core.mailer import InMemoryMailer
from app.services import auth as auth_service
from tests.integration.auth_helpers import (
    EMAIL,
    PASSWORD,
    PREFIX,
    create_user,
    error_of,
    login,
    scalar,
    sql,
)

pytestmark = pytest.mark.integration

WRONG = "not-the-right-password"


@pytest.fixture
def user(api: TestClient, mailer: InMemoryMailer) -> None:
    create_user(api, mailer)
    api.cookies.clear()


def _spy_on_verify(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Records each real password check the login service performs."""
    calls: list[str] = []
    real_verify = security.verify_password

    def spy(password_hash: str, password: str) -> bool:
        calls.append("v")
        return real_verify(password_hash, password)

    monkeypatch.setattr(auth_service, "verify_password", spy)
    return calls


def _set_cookies(response: Any) -> dict[str, str]:
    return {h.split("=", 1)[0]: h for h in response.headers.get_list("set-cookie")}


def test_login_returns_the_user_a_csrf_token_and_the_two_cookies(
    api: TestClient, user: None
) -> None:
    response = login(api)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"user", "csrf_token"}
    assert set(body["user"]) == {"id", "email", "display_name", "email_verified", "platform_role"}
    assert body["user"]["email"] == EMAIL
    assert body["user"]["email_verified"] is True
    assert body["user"]["platform_role"] is None
    assert "password" not in response.text
    assert response.headers["Cache-Control"] == "no-store"

    cookies = _set_cookies(response)
    session_cookie = cookies["cs_session"].lower()
    assert "httponly" in session_cookie
    assert "samesite=lax" in session_cookie
    assert "path=/" in session_cookie
    csrf_cookie = cookies["cs_csrf"].lower()
    assert "httponly" not in csrf_cookie
    assert api.cookies.get("cs_csrf") == body["csrf_token"]


def test_only_a_hash_of_the_session_cookie_is_stored(
    api: TestClient, user: None, conn: Connection
) -> None:
    login(api)
    cookie = api.cookies.get("cs_session")
    assert cookie and len(cookie) >= 43
    stored = bytes(scalar(conn, "SELECT id_hash FROM sessions"))
    assert stored == hashlib.sha256(cookie.encode()).digest()
    assert cookie.encode() not in stored


def test_a_standard_session_lasts_thirty_days(
    api: TestClient, user: None, conn: Connection
) -> None:
    login(api)
    assert scalar(conn, "SELECT expires_at - created_at = interval '30 days' FROM sessions") is True


def test_platform_admin_sessions_get_the_shorter_limits(
    api: TestClient, user: None, conn: Connection
) -> None:
    sql(conn, "UPDATE users SET platform_role = 'PLATFORM_ADMIN'")
    response = login(api)
    assert response.json()["user"]["platform_role"] == "PLATFORM_ADMIN"
    assert scalar(conn, "SELECT expires_at - created_at = interval '7 days' FROM sessions") is True


def test_signed_in_user_can_read_me(api: TestClient, user: None) -> None:
    login(api)
    response = api.get(f"{PREFIX}/me")
    assert response.status_code == 200
    assert response.json()["user"]["email"] == EMAIL


# --- failures never say which part was wrong ---------------------------------------------


def _without_request_id(response: Any) -> dict[str, Any]:
    error = error_of(response)
    return {k: v for k, v in error.items() if k != "request_id"}


def test_wrong_password_and_unknown_email_are_indistinguishable(
    api: TestClient, user: None
) -> None:
    wrong_password = login(api, password=WRONG)
    unknown_email = login(api, email="nobody@northfield.example")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert _without_request_id(wrong_password) == _without_request_id(unknown_email)
    assert error_of(wrong_password)["code"] == "invalid_credentials"
    assert error_of(wrong_password)["message"] == "Email or password is incorrect."
    assert "set-cookie" not in wrong_password.headers


@pytest.mark.parametrize("status", ["SUSPENDED", "DEACTIVATED"])
def test_only_active_accounts_can_sign_in_and_the_reply_is_generic(
    api: TestClient, user: None, conn: Connection, status: str
) -> None:
    sql(conn, "UPDATE users SET status = :s", s=status)
    blocked = login(api)
    assert blocked.status_code == 401
    assert _without_request_id(blocked) == _without_request_id(login(api, password=WRONG))
    assert scalar(conn, "SELECT count(*) FROM sessions") == 0


def test_a_suspension_ends_an_existing_session_on_its_next_request(
    api: TestClient, user: None, conn: Connection
) -> None:
    login(api)
    assert api.get(f"{PREFIX}/me").status_code == 200
    sql(conn, "UPDATE users SET status = 'SUSPENDED'")
    assert api.get(f"{PREFIX}/me").status_code == 401
    assert scalar(conn, "SELECT count(*) FROM sessions") == 0


def test_unknown_emails_cost_the_same_hashing_work(
    api: TestClient, user: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"burn": 0, "verify": 0}
    real_burn, real_verify = security.burn_password_check, security.verify_password

    def burn(password: str) -> None:
        calls["burn"] += 1
        real_burn(password)

    def verify(password_hash: str, password: str) -> bool:
        calls["verify"] += 1
        return real_verify(password_hash, password)

    monkeypatch.setattr(auth_service, "burn_password_check", burn)
    monkeypatch.setattr(auth_service, "verify_password", verify)
    login(api, email="nobody@northfield.example", password=WRONG)
    assert calls == {"burn": 1, "verify": 0}
    login(api, password=WRONG)
    assert calls == {"burn": 1, "verify": 1}


def test_suspended_accounts_still_cost_a_real_password_check(
    api: TestClient, user: None, conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql(conn, "UPDATE users SET status = 'SUSPENDED'")
    calls = _spy_on_verify(monkeypatch)
    login(api)
    assert calls == ["v"]


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"email": EMAIL, "password": PASSWORD, "remember": True}, 422),
        ({"email": EMAIL, "password": "x" * 129}, 422),
        ({"email": EMAIL}, 422),
        ({"email": "bad", "password": PASSWORD}, 422),
    ],
)
def test_malformed_logins_are_validation_errors(
    api: TestClient, user: None, payload: dict[str, Any], status: int
) -> None:
    assert api.post(f"{PREFIX}/auth/login", json=payload).status_code == status


# --- lockouts (AUTH-007) -----------------------------------------------------------------


def _fail(api: TestClient, times: int, email: str = EMAIL) -> list[int]:
    return [login(api, email=email, password=WRONG).status_code for _ in range(times)]


@pytest.mark.parametrize("email", [EMAIL, "nobody@northfield.example"])
def test_five_failures_per_email_then_locked_whether_or_not_the_account_exists(
    api: TestClient, user: None, email: str
) -> None:
    assert _fail(api, 5, email) == [401] * 5
    locked = login(api, email=email, password=WRONG)
    assert locked.status_code == 429
    assert error_of(locked)["code"] == "rate_limited"
    assert 0 < int(locked.headers["Retry-After"]) <= 900


def test_the_lockout_refuses_even_the_correct_password_without_checking_it(
    api: TestClient, user: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail(api, 5)
    calls = _spy_on_verify(monkeypatch)
    assert login(api).status_code == 429
    assert calls == []


def test_emails_are_counted_case_insensitively(api: TestClient, user: None) -> None:
    for email in [
        "Aarav@northfield.example",
        "AARAV@NORTHFIELD.EXAMPLE",
        EMAIL,
        "aarav@Northfield.example",
        " aarav@northfield.example ",
    ]:
        login(api, email=email, password=WRONG)
    assert login(api, email="aArAv@northfield.example").status_code == 429


def test_the_lockout_ends_when_the_window_does(api: TestClient, user: None, clock: Any) -> None:
    _fail(api, 5)
    assert login(api).status_code == 429
    clock.advance(minutes=15)
    assert login(api).status_code == 200


def test_twenty_failures_per_client_across_different_emails(api: TestClient, user: None) -> None:
    statuses = [
        login(api, email=f"person{i}@northfield.example", password=WRONG).status_code
        for i in range(20)
    ]
    assert statuses == [401] * 20
    # A fresh email, and even the right credentials, are refused from this client.
    assert login(api, email="another@northfield.example", password=WRONG).status_code == 429
    assert login(api).status_code == 429


def test_a_successful_login_clears_the_failed_attempts_for_that_email(
    api: TestClient, user: None
) -> None:
    assert _fail(api, 4) == [401] * 4
    assert login(api).status_code == 200
    # Four more failures would have been the 5th-8th without the reset: now still allowed.
    assert _fail(api, 4) == [401] * 4
    assert login(api).status_code == 200


def test_the_threshold_is_audited_once_without_personal_data(
    api: TestClient, user: None, conn: Connection
) -> None:
    _fail(api, 8)  # 5 failures, then 429s that don't count
    rows = sql(
        conn,
        "SELECT action, target_type, target_id, actor_user_id, metadata::text "
        "FROM audit_log WHERE action = 'auth.login_rate_limited'",
    ).all()
    assert len(rows) == 1
    _action, target_type, target_id, actor, metadata = rows[0]
    assert target_type == "user"
    assert target_id == str(scalar(conn, "SELECT id FROM users"))
    assert actor is None
    assert '"scope": "email"' in metadata
    assert '"attempts": 5' in metadata
    for secret in (EMAIL, "aarav", PASSWORD, WRONG):
        assert secret not in metadata


def test_a_lockout_on_an_unknown_email_is_audited_without_naming_anyone(
    api: TestClient, user: None, conn: Connection
) -> None:
    _fail(api, 5, email="nobody@northfield.example")
    row = sql(conn, "SELECT target_type, target_id, metadata::text FROM audit_log").one()
    assert row[0] is None and row[1] is None
    assert "nobody" not in row[2]


def test_the_client_threshold_is_audited_too(api: TestClient, user: None, conn: Connection) -> None:
    for i in range(20):
        login(api, email=f"person{i}@northfield.example", password=WRONG)
    scopes = [r[0] for r in sql(conn, "SELECT metadata->>'scope' FROM audit_log").all()]
    assert scopes == ["ip"]


def test_a_refused_origin_never_touches_the_counters(
    bare_api: TestClient, user: None, conn: Connection
) -> None:
    before = scalar(conn, "SELECT coalesce(sum(count), 0) FROM rate_limit_counters")
    for _ in range(10):
        response = bare_api.post(f"{PREFIX}/auth/login", json={"email": EMAIL, "password": WRONG})
        assert response.status_code == 403
    assert scalar(conn, "SELECT coalesce(sum(count), 0) FROM rate_limit_counters") == before


# --- sessions are never reused -----------------------------------------------------------


def test_signing_in_again_replaces_the_session(
    api: TestClient, user: None, conn: Connection
) -> None:
    login(api)
    first = api.cookies.get("cs_session")
    login(api)
    second = api.cookies.get("cs_session")
    assert first and second and first != second
    assert scalar(conn, "SELECT count(*) FROM sessions") == 1
    api.cookies.set("cs_session", first)
    assert api.get(f"{PREFIX}/me").status_code == 401


def test_a_planted_session_cookie_is_never_adopted(
    api: TestClient, user: None, conn: Connection
) -> None:
    planted = "attacker-chosen-session-id-0123456789abcdefghijk"
    api.cookies.set("cs_session", planted, domain="testserver.local")
    login(api)
    assert api.cookies.get("cs_session") != planted
    digest = hashlib.sha256(planted.encode()).hexdigest()
    assert (
        scalar(conn, "SELECT count(*) FROM sessions WHERE encode(id_hash, 'hex') = :d", d=digest)
        == 0
    )


def test_logging_in_upgrades_a_weaker_password_hash(
    api: TestClient, user: None, conn: Connection
) -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8 * 1024).hash(PASSWORD)
    sql(conn, "UPDATE users SET password_hash = :h", h=weak)
    assert login(api).status_code == 200
    upgraded = scalar(conn, "SELECT password_hash FROM users")
    assert upgraded.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    api.cookies.clear()
    assert login(api).status_code == 200  # the new hash verifies


def test_apps_with_trusted_proxies_count_clients_separately(
    app_factory: Any, mailer: InMemoryMailer, auth_app: FastAPI
) -> None:
    app = app_factory(trusted_proxy_count=1)
    from tests.conftest import APP_ORIGIN

    with TestClient(app, raise_server_exceptions=False, headers={"Origin": APP_ORIGIN}) as client:
        for i in range(20):
            client.post(
                f"{PREFIX}/auth/login",
                json={"email": f"x{i}@northfield.example", "password": WRONG},
                headers={"X-Forwarded-For": "198.51.100.1"},
            )
        blocked = client.post(
            f"{PREFIX}/auth/login",
            json={"email": "y@northfield.example", "password": WRONG},
            headers={"X-Forwarded-For": "198.51.100.1"},
        )
        elsewhere = client.post(
            f"{PREFIX}/auth/login",
            json={"email": "z@northfield.example", "password": WRONG},
            headers={"X-Forwarded-For": "198.51.100.2"},
        )
    assert blocked.status_code == 429
    assert elsewhere.status_code == 401
