"""Server-side sessions (PRD AUTH-004/005/009, AUTH-013; architecture.md §10).

The cookie holds a random 256-bit token; the database holds only its SHA-256 digest, so a
database leak does not yield usable sessions. Each session also has a random CSRF secret.
Status and role are read from the database on every request, never cached in the session.
"""

import base64
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import new_token, token_digest
from app.models.auth_session import AuthSession
from app.models.user import User
from app.policies.auth import can_sign_in
from app.policies.campus import uses_privileged_session_limits
from app.repositories.memberships import holds_privileged_role

SESSION_COOKIE = "cs_session"
CSRF_COOKIE = "cs_csrf"
CSRF_HEADER = "X-CSRF-Token"

# last_seen_at is written at most this often, to avoid a write on every request.
# Idle expiry is therefore accurate to within this interval (architecture.md §10).
TOUCH_INTERVAL = timedelta(minutes=5)
CSRF_SECRET_BYTES = 32


@dataclass(frozen=True)
class SessionLimits:
    idle: timedelta
    absolute: timedelta


@dataclass(frozen=True)
class IssuedSession:
    token: str  # the cookie value; shown to the browser once, never stored
    csrf_token: str
    max_age_seconds: int


@dataclass(frozen=True)
class LoadedSession:
    user: User
    session: AuthSession


def limits_for(user: User, settings: Settings, *, privileged_role: bool) -> SessionLimits:
    """Standard or privileged limits (AUTH-013, P-10). `privileged_role` is whether the user
    holds a privileged college role right now; callers read it fresh on every request."""
    if uses_privileged_session_limits(user, privileged_role):
        return SessionLimits(
            idle=timedelta(hours=settings.privileged_session_idle_hours),
            absolute=timedelta(days=settings.privileged_session_absolute_days),
        )
    return SessionLimits(
        idle=timedelta(days=settings.session_idle_days),
        absolute=timedelta(days=settings.session_absolute_days),
    )


def csrf_token_for(secret: bytes) -> str:
    return base64.urlsafe_b64encode(secret).rstrip(b"=").decode("ascii")


def create_session(db: Session, user: User, settings: Settings, now: datetime) -> IssuedSession:
    """Add a new session to `db` (the caller commits). Always a fresh ID: sessions are
    never reused across sign-in or password changes, which prevents session fixation."""
    token, digest = new_token()
    secret = secrets.token_bytes(CSRF_SECRET_BYTES)
    limits = limits_for(user, settings, privileged_role=holds_privileged_role(db, user.id))
    db.add(
        AuthSession(
            id_hash=digest,
            user_id=user.id,
            csrf_secret=secret,
            created_at=now,
            last_seen_at=now,
            expires_at=now + limits.absolute,
        )
    )
    return IssuedSession(
        token=token,
        csrf_token=csrf_token_for(secret),
        max_age_seconds=int(limits.absolute.total_seconds()),
    )


def load_session(
    db: Session, token: str, settings: Settings, now: datetime
) -> LoadedSession | None:
    """The live session for a cookie value, or None. Dead sessions are deleted on sight."""
    row = db.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.id_hash == token_digest(token))
    ).first()
    if row is None:
        return None
    session, user = row
    limits = limits_for(user, settings, privileged_role=holds_privileged_role(db, user.id))
    expired = (
        now >= session.expires_at
        or now >= session.created_at + limits.absolute
        or now >= session.last_seen_at + limits.idle
    )
    if expired or not can_sign_in(user):
        db.delete(session)
        db.commit()
        return None
    if now - session.last_seen_at >= TOUCH_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return LoadedSession(user=user, session=session)


def revoke_session(db: Session, session_id_hash: bytes) -> None:
    db.execute(delete(AuthSession).where(AuthSession.id_hash == session_id_hash))


def revoke_session_by_token(db: Session, token: str) -> None:
    revoke_session(db, token_digest(token))


def revoke_other_sessions(db: Session, user_id: object, *, keep: bytes | None) -> None:
    """Delete the user's sessions except the one whose digest is `keep` (if any)."""
    statement = delete(AuthSession).where(AuthSession.user_id == user_id)
    if keep is not None:
        statement = statement.where(AuthSession.id_hash != keep)
    db.execute(statement)


def revoke_all_sessions(db: Session, user_id: object) -> None:
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
