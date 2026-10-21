"""Session limits, CSRF tokens, cookie flags and the sign-in policy. No database."""

import base64
from datetime import timedelta

import pytest
from fastapi import Response

from app.api.cookies import clear_session_cookies, set_csrf_cookie, set_session_cookies
from app.models.user import PlatformRole, User, UserStatus
from app.policies.auth import can_sign_in
from app.services.sessions import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    IssuedSession,
    csrf_token_for,
    is_privileged,
    limits_for,
)
from tests.conftest import make_settings


def _user(**fields: object) -> User:
    return User(email="a@b.example", password_hash="x", display_name="A", **fields)


def test_standard_users_get_the_prd_limits() -> None:
    limits = limits_for(_user(), make_settings())
    assert (limits.idle, limits.absolute) == (timedelta(days=7), timedelta(days=30))


def test_platform_admins_always_get_the_privileged_limits() -> None:
    admin = _user(platform_role=PlatformRole.PLATFORM_ADMIN)
    assert is_privileged(admin)
    limits = limits_for(admin, make_settings())
    assert (limits.idle, limits.absolute) == (timedelta(hours=24), timedelta(days=7))
    assert not is_privileged(_user())


def test_limits_follow_configuration() -> None:
    settings = make_settings(session_idle_days=2, session_absolute_days=10)
    limits = limits_for(_user(), settings)
    assert (limits.idle, limits.absolute) == (timedelta(days=2), timedelta(days=10))


def test_csrf_token_is_urlsafe_unpadded_and_decodes_to_the_secret() -> None:
    secret = bytes(range(32))
    token = csrf_token_for(secret)
    assert "=" not in token
    assert base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)) == secret
    assert csrf_token_for(secret) == token
    assert csrf_token_for(bytes(32)) != token


@pytest.mark.parametrize(
    ("status", "allowed"),
    [(UserStatus.ACTIVE, True), (UserStatus.SUSPENDED, False), (UserStatus.DEACTIVATED, False)],
)
def test_only_active_accounts_may_sign_in(status: UserStatus, allowed: bool) -> None:
    assert can_sign_in(_user(status=status)) is allowed


def _cookies(response: Response) -> dict[str, str]:
    """Set-Cookie headers by cookie name."""
    return {h.split("=", 1)[0]: h for h in response.headers.getlist("set-cookie")}


ISSUED = IssuedSession(
    token="session-token-value", csrf_token="csrf-token-value", max_age_seconds=3600
)


def test_session_cookie_is_httponly_lax_and_scoped_to_the_whole_site() -> None:
    response = Response()
    set_session_cookies(
        response,
        make_settings(
            app_env="production",
            app_origin="https://c.example",
            email_backend="smtp",
            smtp_security="tls",
        ),
        ISSUED,
    )
    session = _cookies(response)[SESSION_COOKIE].lower()
    assert "httponly" in session
    assert "samesite=lax" in session
    assert "path=/" in session
    assert "max-age=3600" in session
    assert "secure" in session


def test_csrf_cookie_is_readable_by_scripts() -> None:
    response = Response()
    set_session_cookies(
        response,
        make_settings(
            app_env="production",
            app_origin="https://c.example",
            email_backend="smtp",
            smtp_security="tls",
        ),
        ISSUED,
    )
    csrf = _cookies(response)[CSRF_COOKIE].lower()
    assert "httponly" not in csrf
    assert "secure" in csrf
    assert "samesite=lax" in csrf


@pytest.mark.parametrize("env", ["local", "ci"])
def test_cookies_are_not_secure_only_for_local_http_environments(env: str) -> None:
    response = Response()
    set_session_cookies(response, make_settings(app_env=env), ISSUED)
    for header in _cookies(response).values():
        assert "secure" not in header.lower()


@pytest.mark.parametrize("env", ["staging", "production"])
def test_deployed_environments_always_set_secure(env: str) -> None:
    response = Response()
    settings = make_settings(
        app_env=env, app_origin="https://c.example", email_backend="smtp", smtp_security="starttls"
    )
    set_session_cookies(response, settings, ISSUED)
    set_csrf_cookie(response, settings, "other", 60)
    assert all("secure" in h.lower() for h in response.headers.getlist("set-cookie"))


def test_clearing_expires_both_cookies_with_matching_attributes() -> None:
    response = Response()
    clear_session_cookies(response, make_settings())
    cookies = _cookies(response)
    assert set(cookies) == {SESSION_COOKIE, CSRF_COOKIE}
    for header in cookies.values():
        assert "max-age=0" in header.lower()
        assert "path=/" in header.lower()
    assert "httponly" in cookies[SESSION_COOKIE].lower()
