"""Shared FastAPI dependencies. `current_session` is the access check every protected
route depends on; the route-inventory test fails if a non-public route lacks it."""

import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, cast

from fastapi import Depends, Request, Response, Security
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import get_session
from app.core.errors import Forbidden, NotAuthenticated
from app.core.mailer import Mailer
from app.core.ratelimit import hashed_key
from app.core.request_guards import client_address
from app.models.auth_session import AuthSession
from app.models.user import User
from app.services.sessions import (
    CSRF_HEADER,
    SESSION_COOKIE,
    LoadedSession,
    csrf_token_for,
    load_session,
)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Declares the session cookie as a security scheme so OpenAPI shows which operations need a
# session. current_session still does the checking; the route inventory relies on the scheme.
SESSION_SCHEME_NAME = "SessionCookie"
session_cookie_scheme = APIKeyCookie(
    name=SESSION_COOKIE, scheme_name=SESSION_SCHEME_NAME, auto_error=False
)

Db = Annotated[Session, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


AppSettings = Annotated[Settings, Depends(get_app_settings)]


def get_now(request: Request) -> datetime:
    """The app's clock (replaceable in tests so expiry rules can be exercised)."""
    return cast(datetime, request.app.state.clock())


def get_mailer(request: Request) -> Mailer:
    return cast(Mailer, request.app.state.mailer)


def get_ip_key(request: Request, settings: AppSettings) -> str:
    """Hashed client address for rate limits (no raw IPs in the database)."""
    return hashed_key(client_address(request, settings.trusted_proxy_count))


def no_store(response: Response) -> None:
    """Auth responses carry personal data and tokens: never cache them."""
    response.headers["Cache-Control"] = "no-store"


Now = Annotated[datetime, Depends(get_now)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]
IpKey = Annotated[str, Depends(get_ip_key)]


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession


def _csrf_matches(supplied: str | None, session: AuthSession) -> bool:
    if not supplied:
        return False
    expected = csrf_token_for(session.csrf_secret)
    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


def _loaded(
    request: Request, db: Session, settings: Settings, now: datetime
) -> LoadedSession | None:
    token = request.cookies.get(SESSION_COOKIE)
    return load_session(db, token, settings, now) if token else None


def optional_session(
    request: Request, db: Db, settings: AppSettings, now: Now
) -> AuthContext | None:
    """The signed-in user if there is a live session; never raises. Read-only routes only."""
    loaded = _loaded(request, db, settings, now)
    return AuthContext(user=loaded.user, session=loaded.session) if loaded else None


def current_session(
    request: Request,
    db: Db,
    settings: AppSettings,
    now: Now,
    _scheme: Annotated[str | None, Security(session_cookie_scheme)] = None,
) -> AuthContext:
    """Require a live session of an ACTIVE account (401 otherwise). State-changing requests
    must also present the session's CSRF token in `X-CSRF-Token` (403 otherwise)."""
    loaded = _loaded(request, db, settings, now)
    if loaded is None:
        raise NotAuthenticated()
    if request.method not in SAFE_METHODS and not _csrf_matches(
        request.headers.get(CSRF_HEADER), loaded.session
    ):
        raise Forbidden("Reload the page and try again.", code="csrf_failed")
    return AuthContext(user=loaded.user, session=loaded.session)


Auth = Annotated[AuthContext, Depends(current_session)]
OptionalAuth = Annotated[AuthContext | None, Depends(optional_session)]
