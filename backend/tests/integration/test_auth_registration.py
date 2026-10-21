"""Registration and email verification (PRD AUTH-001/002/003, US-01) on the local test database."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.core.mailer import InMemoryMailer, OutgoingEmail
from tests.integration.auth_helpers import (
    EMAIL,
    NAME,
    PASSWORD,
    PREFIX,
    create_user,
    csrf,
    error_of,
    login,
    register,
    scalar,
    token_from,
    verify,
)

pytestmark = pytest.mark.integration


def test_new_account_gets_201_and_one_verification_email(
    api: TestClient, mailer: InMemoryMailer, conn: Connection
) -> None:
    response = register(api)
    assert response.status_code == 201
    assert response.json() == {"message": "Check your email to finish setting up your account."}
    assert len(mailer.outbox) == 1
    email = mailer.outbox[0]
    assert email.to == EMAIL
    assert email.subject == "Verify your CampusSignal email"
    assert f"http://localhost:5173/verify-email#token={token_from(mailer)}" in email.text
    assert scalar(conn, "SELECT status FROM users WHERE email = :e", e=EMAIL) == "ACTIVE"
    assert scalar(conn, "SELECT email_verified_at FROM users WHERE email = :e", e=EMAIL) is None


def test_the_password_is_stored_as_argon2id_and_never_returned_or_mailed(
    api: TestClient, mailer: InMemoryMailer, conn: Connection
) -> None:
    response = register(api)
    stored = scalar(conn, "SELECT password_hash FROM users WHERE email = :e", e=EMAIL)
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored
    assert PASSWORD not in response.text
    assert all(PASSWORD not in email.text for email in mailer.outbox)


def test_existing_email_in_any_case_looks_identical_and_creates_no_second_account(
    api: TestClient, mailer: InMemoryMailer, conn: Connection
) -> None:
    first = register(api)
    mailer.outbox.clear()
    second = register(api, email="Aarav@NORTHFIELD.example", name="Someone Else")
    assert (second.status_code, second.json()) == (first.status_code, first.json())
    assert scalar(conn, "SELECT count(*) FROM users") == 1
    assert scalar(conn, "SELECT display_name FROM users") == NAME  # untouched


def test_existing_owner_gets_a_notice_not_a_verification_link(
    api: TestClient, mailer: InMemoryMailer
) -> None:
    register(api)
    mailer.outbox.clear()
    register(api)
    assert len(mailer.outbox) == 1
    notice = mailer.outbox[0]
    assert notice.to == EMAIL
    assert notice.subject == "Someone tried to register with your email"
    assert "#token=" not in notice.text
    assert "/forgot-password" in notice.text


def test_notices_to_an_existing_owner_are_capped_per_hour_without_changing_the_reply(
    api: TestClient, mailer: InMemoryMailer
) -> None:
    register(api)
    mailer.outbox.clear()
    statuses = [register(api).status_code for _ in range(5)]
    assert statuses == [201] * 5
    assert len(mailer.outbox) == 3  # an inbox can't be flooded through this endpoint


@pytest.mark.parametrize(
    ("password", "message"),
    [
        ("password1234", "This password is too common. Choose one that's harder to guess."),
        ("PASSWORD1234", "This password is too common. Choose one that's harder to guess."),
        ("short", "Use at least 10 characters."),
        ("aarav.nair.2026", "Don't use your email address in your password."),
    ],
)
def test_weak_passwords_get_a_field_level_error_and_no_account(
    api: TestClient, conn: Connection, mailer: InMemoryMailer, password: str, message: str
) -> None:
    response = register(api, password=password)
    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "validation_error"
    assert error["details"] == [{"field": "password", "message": message}]
    assert scalar(conn, "SELECT count(*) FROM users") == 0
    assert mailer.outbox == []
    assert password not in response.text  # the input is never echoed back


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"email": "not-an-email", "password": PASSWORD, "display_name": NAME}, "email"),
        ({"email": EMAIL, "password": PASSWORD, "display_name": ""}, "display_name"),
        ({"email": EMAIL, "password": "x" * 129, "display_name": NAME}, "password"),
        ({"email": EMAIL, "password": PASSWORD}, "display_name"),
    ],
)
def test_schema_errors_name_the_field(api: TestClient, payload: dict[str, Any], field: str) -> None:
    response = api.post(f"{PREFIX}/auth/register", json=payload)
    assert response.status_code == 422
    assert field in {d["field"] for d in error_of(response)["details"]}


@pytest.mark.parametrize(
    "extra", [{"platform_role": "PLATFORM_ADMIN"}, {"status": "ACTIVE"}, {"email_verified": True}]
)
def test_a_client_cannot_set_privileged_fields(
    api: TestClient, conn: Connection, extra: dict[str, Any]
) -> None:
    body = {"email": EMAIL, "password": PASSWORD, "display_name": NAME, **extra}
    response = api.post(f"{PREFIX}/auth/register", json=body)
    assert response.status_code == 422
    assert scalar(conn, "SELECT count(*) FROM users") == 0


def test_registration_is_rate_limited_per_client(api: TestClient, mailer: InMemoryMailer) -> None:
    statuses = [register(api, email=f"user{i}@northfield.example").status_code for i in range(11)]
    assert statuses[:10] == [201] * 10
    assert statuses[10] == 429
    blocked = register(api, email="user99@northfield.example")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert error_of(blocked)["code"] == "rate_limited"


def test_a_failing_mail_server_does_not_change_the_reply_or_leak_into_logs(
    auth_app: FastAPI, api: TestClient, conn: Connection, caplog: pytest.LogCaptureFixture
) -> None:
    class BrokenMailer:
        def send(self, email: OutgoingEmail) -> None:
            raise ConnectionRefusedError(f"cannot deliver to {email.to}: {email.text}")

    auth_app.state.mailer = BrokenMailer()
    with caplog.at_level("DEBUG"):
        response = register(api)
    assert response.status_code == 201
    assert scalar(conn, "SELECT count(*) FROM users") == 1
    logged = " ".join(str(record.__dict__) for record in caplog.records)
    assert "email_send_failed" in logged
    assert "ConnectionRefusedError" in logged
    assert EMAIL not in logged
    assert "#token=" not in logged


# --- verification ------------------------------------------------------------------------


def test_verifying_marks_the_email_verified(
    api: TestClient, mailer: InMemoryMailer, conn: Connection
) -> None:
    register(api)
    response = verify(api, token_from(mailer))
    assert response.status_code == 200
    assert response.json() == {"message": "Your email is verified."}
    assert scalar(conn, "SELECT email_verified_at FROM users WHERE email = :e", e=EMAIL) is not None


def test_the_token_is_stored_only_as_a_hash_and_is_single_use(
    api: TestClient, mailer: InMemoryMailer, conn: Connection
) -> None:
    register(api)
    token = token_from(mailer)
    assert len(token) >= 43
    stored = scalar(conn, "SELECT token_hash FROM user_tokens")
    assert bytes(stored) != token.encode()
    assert token not in str(bytes(stored))

    assert verify(api, token).status_code == 200
    again = verify(api, token)
    assert again.status_code == 400
    assert error_of(again)["code"] == "token_used"  # "link already used" (US-01)


def test_an_expired_link_says_so(api: TestClient, mailer: InMemoryMailer, clock: Any) -> None:
    register(api)
    token = token_from(mailer)
    clock.advance(hours=24, seconds=1)
    response = verify(api, token)
    assert response.status_code == 400
    assert error_of(response)["code"] == "token_expired"


def test_a_link_works_until_the_last_moment(
    api: TestClient, mailer: InMemoryMailer, clock: Any
) -> None:
    register(api)
    token = token_from(mailer)
    clock.advance(hours=23, minutes=59)
    assert verify(api, token).status_code == 200


@pytest.mark.parametrize("token", ["garbage", "a" * 43, "x" * 200])
def test_an_unknown_token_is_invalid(api: TestClient, token: str) -> None:
    response = verify(api, token)
    assert response.status_code == 400
    assert error_of(response)["code"] == "token_invalid"


def test_a_password_reset_token_cannot_verify_an_email(
    api: TestClient, mailer: InMemoryMailer, conn: Connection
) -> None:
    create_user(api, mailer, verified=False)
    api.post(f"{PREFIX}/auth/password-reset/request", json={"email": EMAIL})
    reset_token = token_from(mailer)
    response = verify(api, reset_token)
    assert error_of(response)["code"] == "token_invalid"
    assert scalar(conn, "SELECT email_verified_at FROM users") is None


def test_verification_attempts_are_rate_limited_per_client(api: TestClient) -> None:
    statuses = [verify(api, f"guess-{i}").status_code for i in range(31)]
    assert statuses[:30] == [400] * 30
    assert statuses[30] == 429


def test_unverified_accounts_can_sign_in(api: TestClient, mailer: InMemoryMailer) -> None:
    create_user(api, mailer, verified=False)
    response = login(api)
    assert response.status_code == 200
    assert response.json()["user"]["email_verified"] is False


# --- resend ------------------------------------------------------------------------------


def test_resend_needs_a_session(api: TestClient) -> None:
    assert api.post(f"{PREFIX}/auth/resend-verification").status_code == 401


def test_resend_sends_a_new_link_and_retires_the_old_one(
    api: TestClient, mailer: InMemoryMailer
) -> None:
    register(api)
    first_token = token_from(mailer)
    login(api)
    mailer.outbox.clear()
    response = api.post(f"{PREFIX}/auth/resend-verification", headers=csrf(api))
    assert response.status_code == 202
    assert len(mailer.outbox) == 1
    assert mailer.outbox[0].to == EMAIL
    new_token = token_from(mailer)
    assert new_token != first_token
    assert error_of(verify(api, first_token))["code"] == "token_invalid"
    assert verify(api, new_token).status_code == 200


def test_resend_is_limited_to_three_per_hour_then_resets(
    api: TestClient, mailer: InMemoryMailer, clock: Any
) -> None:
    create_user(api, mailer, verified=False)
    login(api)
    statuses = [
        api.post(f"{PREFIX}/auth/resend-verification", headers=csrf(api)).status_code
        for _ in range(4)
    ]
    assert statuses == [202, 202, 202, 429]
    clock.advance(hours=1)
    assert api.post(f"{PREFIX}/auth/resend-verification", headers=csrf(api)).status_code == 202


def test_resend_for_a_verified_account_is_a_conflict(
    api: TestClient, mailer: InMemoryMailer
) -> None:
    create_user(api, mailer, verified=True)
    login(api)
    response = api.post(f"{PREFIX}/auth/resend-verification", headers=csrf(api))
    assert response.status_code == 409
    assert error_of(response)["code"] == "already_verified"
    assert mailer.outbox == []


def test_old_unused_tokens_are_deleted_not_accumulated(
    api: TestClient, mailer: InMemoryMailer, conn: Connection
) -> None:
    create_user(api, mailer, verified=False)
    login(api)
    for _ in range(3):
        api.post(f"{PREFIX}/auth/resend-verification", headers=csrf(api))
    assert scalar(conn, "SELECT count(*) FROM user_tokens WHERE used_at IS NULL") == 1
