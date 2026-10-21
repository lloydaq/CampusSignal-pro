"""Session and CSRF cookies (PRD AUTH-004; architecture.md §10).

`cs_session` is HttpOnly (scripts can't read it), SameSite=Lax, and Secure everywhere except
local development and CI, which run over plain http. `cs_csrf` carries the CSRF token for the
SPA to echo in `X-CSRF-Token`; it must be readable by scripts, so it is not HttpOnly.
"""

from fastapi import Response

from app.core.config import Settings
from app.services.sessions import CSRF_COOKIE, SESSION_COOKIE, IssuedSession


def _secure(settings: Settings) -> bool:
    return settings.app_env not in ("local", "ci")


def set_session_cookies(response: Response, settings: Settings, issued: IssuedSession) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        max_age=issued.max_age_seconds,
        path="/",
        httponly=True,
        secure=_secure(settings),
        samesite="lax",
    )
    set_csrf_cookie(response, settings, issued.csrf_token, issued.max_age_seconds)


def set_csrf_cookie(
    response: Response, settings: Settings, csrf_token: str, max_age_seconds: int
) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age_seconds,
        path="/",
        httponly=False,
        secure=_secure(settings),
        samesite="lax",
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    secure = _secure(settings)
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=secure, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", httponly=False, secure=secure, samesite="lax")
