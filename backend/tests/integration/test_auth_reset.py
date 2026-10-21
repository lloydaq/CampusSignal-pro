"""Password reset (PRD AUTH-006) and what the auth API must never log or audit."""

import logging
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.core.mailer import InMemoryMailer
from tests.integration.auth_helpers import (
    EMAIL,
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
    token_from,
    verify,
)

pytestmark = pytest.mark.integration

REQUEST_MESSAGE = "If an account exists for that email, we've sent a reset link."


@pytest.fixture
def user(api: TestClient, mailer: InMemoryMailer) -> None:
    create_user(api, mailer)
    api.cookies.clear()


def _request(api: TestClient, email: str = EMAIL) -> Any:
    return api.post(f"{PREFIX}/auth/password-reset/request", json={"email": email})


def _confirm(api: TestClient, token: str, password: str = NEW_PASSWORD) -> Any:
    return api.post(
        f"{PREFIX}/auth/password-reset/confirm", json={"token": token, "new_password": password}
    )


# --- requesting a link -------------------------------------------------------------------


def test_a_known_email_gets_a_link_with_the_token_in_the_fragment(
    api: TestClient, user: None, mailer: InMemoryMailer
) -> None:
    response = _request(api)
    assert response.status_code == 202
    assert response.json() == {"message": REQUEST_MESSAGE}
    assert len(mailer.outbox) == 1
    assert mailer.outbox[0].to == EMAIL
    assert (
        f"http://localhost:5173/reset-password#token={token_from(mailer)}" in mailer.outbox[0].text
    )


def test_unknown_suspended_and_deactivated_emails_look_identical_and_get_no_email(
    api: TestClient, user: None, mailer: InMemoryMailer, conn: Connection
) -> None:
    known = _request(api)
    mailer.outbox.clear()
    replies = [_request(api, "nobody@northfield.example")]
    for status in ("SUSPENDED", "DEACTIVATED"):
        sql(conn, "UPDATE users SET status = :s", s=status)
        replies.append(_request(api))
    for reply in replies:
        assert (reply.status_code, reply.json()) == (known.status_code, known.json())
    assert mailer.outbox == []
    assert scalar(conn, "SELECT count(*) FROM user_tokens WHERE purpose = 'RESET_PASSWORD'") == 1


def test_the_email_address_is_matched_case_insensitively(
    api: TestClient, user: None, mailer: InMemoryMailer
) -> None:
    _request(api, "AARAV@Northfield.Example")
    assert len(mailer.outbox) == 1


def test_a_new_request_retires_the_previous_link(
    api: TestClient, user: None, mailer: InMemoryMailer
) -> None:
    _request(api)
    first = token_from(mailer)
    _request(api)
    second = token_from(mailer)
    assert first != second
    assert error_of(_confirm(api, first))["code"] == "token_invalid"
    assert _confirm(api, second).status_code == 200


def test_requests_are_limited_per_email_and_the_reply_never_changes(
    api: TestClient, user: None, mailer: InMemoryMailer
) -> None:
    statuses = [_request(api).status_code for _ in range(5)]
    assert statuses == [202] * 5
    sixth = _request(api)
    assert sixth.status_code == 429
    assert int(sixth.headers["Retry-After"]) > 0
    # the same limit applies to an address that does not exist
    unknown = [_request(api, "nobody@northfield.example").status_code for _ in range(6)]
    assert unknown == [202] * 5 + [429]


def test_requests_are_limited_per_client(api: TestClient, user: None) -> None:
    statuses = [_request(api, f"person{i}@northfield.example").status_code for i in range(21)]
    assert statuses == [202] * 20 + [429]


def test_the_email_limit_resets_after_an_hour(api: TestClient, user: None, clock: Any) -> None:
    for _ in range(5):
        _request(api)
    assert _request(api).status_code == 429
    clock.advance(hours=1)
    assert _request(api).status_code == 202


# --- confirming --------------------------------------------------------------------------


def test_confirming_sets_the_new_password_and_ends_every_session(
    api: TestClient, auth_app: FastAPI, user: None, mailer: InMemoryMailer, conn: Connection
) -> None:
    phone = signed_in(auth_app, mailer)
    login(api)
    _request(api)
    token = token_from(mailer)

    response = _confirm(api, token)
    assert response.status_code == 200
    assert response.json() == {
        "message": "Your password was changed. Sign in with your new password."
    }
    assert "set-cookie" not in response.headers  # resetting never signs anyone in
    assert scalar(conn, "SELECT count(*) FROM sessions") == 0
    assert phone.get(f"{PREFIX}/me").status_code == 401
    assert api.get(f"{PREFIX}/me").status_code == 401

    assert login(api, password=PASSWORD).status_code == 401
    assert login(api, password=NEW_PASSWORD).status_code == 200


def test_the_link_is_single_use(api: TestClient, user: None, mailer: InMemoryMailer) -> None:
    _request(api)
    token = token_from(mailer)
    assert _confirm(api, token).status_code == 200
    again = _confirm(api, token, "another-long-passphrase")
    assert again.status_code == 400
    assert error_of(again)["code"] == "token_used"
    assert login(api, password=NEW_PASSWORD).status_code == 200  # the first change stands


def test_the_link_expires_after_sixty_minutes(
    api: TestClient, user: None, mailer: InMemoryMailer, clock: Any
) -> None:
    _request(api)
    token = token_from(mailer)
    clock.advance(minutes=60, seconds=1)
    response = _confirm(api, token)
    assert response.status_code == 400
    assert error_of(response)["code"] == "token_expired"
    assert login(api).status_code == 200  # the old password still works


def test_the_link_works_until_the_last_minute(
    api: TestClient, user: None, mailer: InMemoryMailer, clock: Any
) -> None:
    _request(api)
    token = token_from(mailer)
    clock.advance(minutes=59)
    assert _confirm(api, token).status_code == 200


@pytest.mark.parametrize("token", ["garbage", "a" * 43])
def test_an_unknown_token_is_invalid(api: TestClient, user: None, token: str) -> None:
    response = _confirm(api, token)
    assert response.status_code == 400
    assert error_of(response)["code"] == "token_invalid"


def test_a_weak_password_is_refused_without_using_up_the_link(
    api: TestClient, user: None, mailer: InMemoryMailer, conn: Connection
) -> None:
    _request(api)
    token = token_from(mailer)
    before = scalar(conn, "SELECT password_hash FROM users")
    weak = _confirm(api, token, "password1234")
    assert weak.status_code == 422
    assert error_of(weak)["details"][0]["field"] == "new_password"
    assert scalar(conn, "SELECT password_hash FROM users") == before
    assert _confirm(api, token).status_code == 200  # the same link still works


def test_a_suspended_account_cannot_reset_and_the_reply_is_the_generic_invalid_link(
    api: TestClient, user: None, mailer: InMemoryMailer, conn: Connection
) -> None:
    _request(api)
    token = token_from(mailer)
    sql(conn, "UPDATE users SET status = 'SUSPENDED'")
    before = scalar(conn, "SELECT password_hash FROM users")
    response = _confirm(api, token)
    assert response.status_code == 400
    assert error_of(response)["code"] == "token_invalid"
    assert scalar(conn, "SELECT password_hash FROM users") == before


def test_resetting_does_not_verify_an_unverified_email(
    api: TestClient, mailer: InMemoryMailer, conn: Connection
) -> None:
    create_user(api, mailer, verified=False)
    _request(api)
    assert _confirm(api, token_from(mailer)).status_code == 200
    assert scalar(conn, "SELECT email_verified_at FROM users") is None
    # ...and a verification link issued earlier is unaffected by the reset
    assert login(api, password=NEW_PASSWORD).json()["user"]["email_verified"] is False


def test_a_verification_link_cannot_reset_a_password(
    api: TestClient, mailer: InMemoryMailer
) -> None:
    create_user(api, mailer, verified=False, email="b@northfield.example")
    api.post(
        f"{PREFIX}/auth/register",
        json={"email": "c@northfield.example", "password": PASSWORD, "display_name": "C"},
    )
    verification_token = token_from(mailer)
    response = _confirm(api, verification_token)
    assert error_of(response)["code"] == "token_invalid"
    assert verify(api, verification_token).status_code == 200  # still a valid verification link


def test_confirmation_attempts_are_limited_per_client(
    api: TestClient, user: None, conn: Connection
) -> None:
    sql(conn, "DELETE FROM rate_limit_counters")  # setup's verification used one attempt
    statuses = [_confirm(api, f"guess-{i}").status_code for i in range(31)]
    assert statuses == [400] * 30 + [429]


def test_resetting_is_audited_without_secrets(
    api: TestClient, user: None, mailer: InMemoryMailer, conn: Connection
) -> None:
    _request(api)
    token = token_from(mailer)
    _confirm(api, token)
    row = sql(
        conn,
        "SELECT target_type, target_id, actor_user_id, metadata::text FROM audit_log "
        "WHERE action = 'auth.password_reset_completed'",
    ).one()
    assert row[0] == "user"
    assert row[1] == str(scalar(conn, "SELECT id FROM users"))
    assert row[2] is None
    assert token not in row[3]
    assert NEW_PASSWORD not in row[3]


def test_old_reset_tokens_are_deleted_after_a_reset(
    api: TestClient, user: None, mailer: InMemoryMailer, conn: Connection
) -> None:
    _request(api)
    token = token_from(mailer)
    _confirm(api, token)
    assert (
        scalar(
            conn,
            "SELECT count(*) FROM user_tokens WHERE purpose = 'RESET_PASSWORD' AND used_at IS NULL",
        )
        == 0
    )


# --- nothing secret reaches the logs or the audit trail ----------------------------------


def test_a_full_account_lifecycle_logs_and_audits_no_secrets(
    api: TestClient,
    auth_app: FastAPI,
    mailer: InMemoryMailer,
    conn: Connection,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secrets_seen: list[str] = []
    with caplog.at_level(logging.DEBUG):
        api.post(
            f"{PREFIX}/auth/register",
            json={"email": EMAIL, "password": PASSWORD, "display_name": "Aarav Nair"},
        )
        verification = token_from(mailer)
        verify(api, verification)
        for _ in range(6):  # trip the limiter so the audit path runs too
            login(api, password="wrong-password-value")
        api.cookies.clear()
        sql(conn, "DELETE FROM rate_limit_counters")
        login(api)
        session_cookie = api.cookies.get("cs_session") or ""
        csrf_token = api.cookies.get("cs_csrf") or ""
        api.post(
            f"{PREFIX}/me/password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=csrf(api),
        )
        api.post(f"{PREFIX}/auth/logout", headers=csrf(api))
        _request(api)
        reset = token_from(mailer)
        _confirm(api, reset, "garden-lantern-oxford")
        secrets_seen = [
            PASSWORD,
            NEW_PASSWORD,
            "garden-lantern-oxford",
            "wrong-password-value",
            verification,
            reset,
            session_cookie,
            csrf_token,
            EMAIL,
        ]

    logged = " ".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
    audit = " ".join(str(row) for row in sql(conn, "SELECT * FROM audit_log").all())
    for secret in secrets_seen:
        assert secret, "a secret was empty, so the check would prove nothing"
        assert secret not in logged
        assert secret not in audit
