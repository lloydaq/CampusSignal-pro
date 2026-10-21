"""Authentication business logic (PRD AUTH-001…010, US-01).

Routers stay thin; everything that decides something lives here. Conventions:

- Functions take `now` so time-dependent rules (expiry, rate windows) are testable.
- Functions commit their own transaction. Rate-limit counters and audit entries are written
  *before* a failure is raised and committed with it, so rejected attempts still count.
- Emails are returned, not sent: the router sends them in the background after the commit.
- No password, token, session value or email address is ever put in a log or audit entry.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.config import Settings
from app.core.errors import (
    BadRequest,
    Conflict,
    InvalidCredentials,
    RateLimited,
    ValidationFailed,
)
from app.core.mailer import OutgoingEmail
from app.core.ratelimit import Limit
from app.core.security import (
    burn_password_check,
    hash_password,
    new_token,
    password_needs_rehash,
    password_problem,
    token_digest,
    verify_password,
)
from app.models.auth_session import AuthSession
from app.models.user import User
from app.models.user_token import TokenPurpose, UserToken
from app.policies.auth import can_sign_in
from app.services import sessions
from app.services.audit import record_audit
from app.services.sessions import IssuedSession

VERIFY_TOKEN_TTL = timedelta(hours=24)
RESET_TOKEN_TTL = timedelta(minutes=60)

_QUARTER_HOUR = timedelta(minutes=15)
_HOUR = timedelta(hours=1)

# Failed sign-ins (AUTH-007): 5 per submitted email and 20 per client address, whether or
# not the account exists, so the lockout does not reveal which emails are registered.
LOGIN_EMAIL = Limit("login:email", 5, _QUARTER_HOUR)
LOGIN_IP = Limit("login:ip", 20, _QUARTER_HOUR)
# Limits for operations the PRD doesn't size, added under Rules R-2.12.
REGISTER_IP = Limit("register:ip", 10, _HOUR)
REGISTRATION_NOTICE = Limit("register:notice", 3, _HOUR)  # "someone tried to register" emails
RESEND_VERIFICATION = Limit("resend:user", 3, _HOUR)  # AUTH-003
RESET_EMAIL = Limit("reset:email", 5, _HOUR)
RESET_IP = Limit("reset:ip", 20, _HOUR)
TOKEN_ATTEMPTS_IP = Limit("token:ip", 30, _QUARTER_HOUR)  # verify-email and reset confirm
PASSWORD_CHANGE_FAILURES = Limit("password:fail", 5, _QUARTER_HOUR)

ACTION_LOGIN_RATE_LIMITED = "auth.login_rate_limited"
ACTION_PASSWORD_CHANGED = "auth.password_changed"  # noqa: S105  (audit action name)
ACTION_PASSWORD_RESET = "auth.password_reset_completed"  # noqa: S105  (audit action name)


@dataclass(frozen=True)
class LoginResult:
    user: User
    session: IssuedSession


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _origin(settings: Settings) -> str:
    return str(settings.app_origin).rstrip("/")


def _find_user(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def _check_new_password(password: str, email: str, field: str) -> None:
    problem = password_problem(password, email=email)
    if problem is not None:
        raise ValidationFailed.field(field, problem)


def issue_token(
    db: Session, user_id: object, purpose: TokenPurpose, ttl: timedelta, now: datetime
) -> str:
    """A new single-use token; older unused tokens for the same purpose stop working."""
    db.execute(
        delete(UserToken).where(
            UserToken.user_id == user_id,
            UserToken.purpose == purpose,
            UserToken.used_at.is_(None),
        )
    )
    token, digest = new_token()
    db.add(
        UserToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=digest,
            created_at=now,
            expires_at=now + ttl,
        )
    )
    return token


def _verification_email(settings: Settings, user: User, token: str) -> OutgoingEmail:
    link = f"{_origin(settings)}/verify-email#token={token}"
    return OutgoingEmail(
        to=user.email,
        subject="Verify your CampusSignal email",
        text=(
            f"Hi {user.display_name},\n\n"
            f"Confirm your email address to finish setting up your account:\n\n{link}\n\n"
            "This link works once and expires in 24 hours. "
            "If you didn't create an account, you can ignore this email.\n"
        ),
    )


def _registration_notice_email(settings: Settings, to: str) -> OutgoingEmail:
    return OutgoingEmail(
        to=to,
        subject="Someone tried to register with your email",
        text=(
            "Someone tried to create a CampusSignal account with this email address, "
            "but you already have one.\n\n"
            f"If it was you, sign in at {_origin(settings)}/sign-in, or reset your password at "
            f"{_origin(settings)}/forgot-password.\n\n"
            "If it wasn't you, you can ignore this email. Your account is unchanged.\n"
        ),
    )


def _reset_email(settings: Settings, user: User, token: str) -> OutgoingEmail:
    link = f"{_origin(settings)}/reset-password#token={token}"
    return OutgoingEmail(
        to=user.email,
        subject="Reset your CampusSignal password",
        text=(
            f"Hi {user.display_name},\n\n"
            f"Use this link to choose a new password:\n\n{link}\n\n"
            "This link works once and expires in 60 minutes. Using it signs you out everywhere. "
            "If you didn't ask for this, you can ignore this email; your password is unchanged.\n"
        ),
    )


# --- registration and email verification -------------------------------------------------


def register(
    db: Session,
    settings: Settings,
    *,
    email: str,
    password: str,
    display_name: str,
    ip_key: str,
    now: datetime,
) -> OutgoingEmail | None:
    """AUTH-001/002/003. Same outcome for new and existing emails (no enumeration):
    a new account gets a verification email, an existing owner gets a notice."""
    email = normalize_email(email)
    ratelimit.consume(db, REGISTER_IP, ip_key, now)
    _check_new_password(password, email, "password")
    password_hash = hash_password(password)  # also for existing emails: equal work either way

    user = User(email=email, password_hash=password_hash, display_name=display_name)
    try:
        with db.begin_nested():
            db.add(user)
            db.flush()
    except IntegrityError:
        # Already registered (or a concurrent registration won the race).
        state = ratelimit.hit(db, REGISTRATION_NOTICE, ratelimit.hashed_key(email), now)
        db.commit()
        if state.count > REGISTRATION_NOTICE.max_hits:
            return None  # an inbox can't be flooded through this endpoint
        return _registration_notice_email(settings, email)

    token = issue_token(db, user.id, TokenPurpose.VERIFY_EMAIL, VERIFY_TOKEN_TTL, now)
    db.commit()
    return _verification_email(settings, user, token)


def _token_error(db: Session, digest: bytes, purpose: TokenPurpose, now: datetime) -> BadRequest:
    """Why a token could not be used. Tokens are 256-bit random, so telling used, expired
    and unknown apart gives a guesser nothing and gives the user a useful message."""
    row = db.execute(
        select(UserToken).where(UserToken.token_hash == digest, UserToken.purpose == purpose)
    ).scalar_one_or_none()
    if row is None:
        return BadRequest("This link isn't valid.", code="token_invalid")
    if row.used_at is not None:
        return BadRequest("This link was already used.", code="token_used")
    if row.expires_at <= now:
        return BadRequest("This link has expired.", code="token_expired")
    return BadRequest("This link isn't valid.", code="token_invalid")


def _consume_token(
    db: Session, digest: bytes, purpose: TokenPurpose, now: datetime
) -> uuid.UUID | None:
    """Mark a token used if (and only if) it is still unused and unexpired, atomically,
    so concurrent requests can never both succeed. Returns the token's user."""
    return db.execute(
        update(UserToken)
        .where(
            UserToken.token_hash == digest,
            UserToken.purpose == purpose,
            UserToken.used_at.is_(None),
            UserToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(UserToken.user_id)
    ).scalar_one_or_none()


def verify_email(db: Session, *, token: str, ip_key: str, now: datetime) -> None:
    ratelimit.consume(db, TOKEN_ATTEMPTS_IP, ip_key, now)
    digest = token_digest(token)
    user_id = _consume_token(db, digest, TokenPurpose.VERIFY_EMAIL, now)
    if user_id is None:
        raise _token_error(db, digest, TokenPurpose.VERIFY_EMAIL, now)
    db.execute(
        update(User)
        .where(User.id == user_id, User.email_verified_at.is_(None))
        .values(email_verified_at=now)
    )
    db.commit()


def resend_verification(
    db: Session, settings: Settings, *, user: User, now: datetime
) -> OutgoingEmail:
    if user.email_verified_at is not None:
        raise Conflict("Your email is already verified.", code="already_verified")
    ratelimit.consume(db, RESEND_VERIFICATION, str(user.id), now)
    token = issue_token(db, user.id, TokenPurpose.VERIFY_EMAIL, VERIFY_TOKEN_TTL, now)
    db.commit()
    return _verification_email(settings, user, token)


# --- sign in and out ---------------------------------------------------------------------


def _audit_lockout(db: Session, *, limit: Limit, scope: str, count: int, user: User | None) -> None:
    """One entry, written by the attempt that used up the limit and then failed (ADMIN-006)."""
    if count == limit.max_hits:
        record_audit(
            db,
            action=ACTION_LOGIN_RATE_LIMITED,
            target_type="user" if user else None,
            target_id=str(user.id) if user else None,
            metadata={"scope": scope, "attempts": count},
        )


def login(
    db: Session,
    settings: Settings,
    *,
    email: str,
    password: str,
    ip_key: str,
    old_session_token: str | None,
    now: datetime,
) -> LoginResult:
    email = normalize_email(email)
    email_key = ratelimit.hashed_key(email)

    # Reserve an attempt on both counters *before* checking the password. The reservation is
    # atomic and committed, so parallel guesses cannot all slip past a check-then-act gap.
    # Refused attempts never reach the password check (AUTH-007).
    email_state = ratelimit.consume(db, LOGIN_EMAIL, email_key, now)
    try:
        ip_state = ratelimit.consume(db, LOGIN_IP, ip_key, now)
    except RateLimited:
        ratelimit.release(db, LOGIN_EMAIL, email_key, now)  # this address's lock, not the email's
        db.commit()
        raise

    user = _find_user(db, email)
    if user is None:
        burn_password_check(password)  # same work as a real check: no timing oracle
        password_ok = False
    else:
        password_ok = verify_password(user.password_hash, password)

    if user is None or not password_ok or not can_sign_in(user):
        _audit_lockout(db, limit=LOGIN_EMAIL, scope="email", count=email_state.count, user=user)
        _audit_lockout(db, limit=LOGIN_IP, scope="ip", count=ip_state.count, user=None)
        db.commit()
        raise InvalidCredentials()

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    ratelimit.clear(db, LOGIN_EMAIL, email_key, now)
    ratelimit.release(db, LOGIN_IP, ip_key, now)  # only failures count against an address
    if old_session_token:
        sessions.revoke_session_by_token(db, old_session_token)  # never reuse a session ID
    issued = sessions.create_session(db, user, settings, now)
    db.commit()
    return LoginResult(user=user, session=issued)


# --- password change and reset -----------------------------------------------------------


def change_password(
    db: Session,
    settings: Settings,
    *,
    user: User,
    current_password: str,
    new_password: str,
    now: datetime,
) -> IssuedSession:
    """AUTH-010. Ends every session (including this one) and issues a fresh one."""
    key = str(user.id)
    # Reserved atomically before the password check (see `login`); a correct password clears it.
    ratelimit.consume(db, PASSWORD_CHANGE_FAILURES, key, now)
    if not verify_password(user.password_hash, current_password):
        raise BadRequest(
            "Your current password is incorrect.",
            code="wrong_password",
            details=[
                {"field": "current_password", "message": "Your current password is incorrect."}
            ],
        )
    ratelimit.clear(db, PASSWORD_CHANGE_FAILURES, key, now)
    db.commit()
    _check_new_password(new_password, user.email, "new_password")

    user.password_hash = hash_password(new_password)
    sessions.revoke_all_sessions(db, user.id)
    issued = sessions.create_session(db, user, settings, now)
    record_audit(
        db,
        action=ACTION_PASSWORD_CHANGED,
        actor_user_id=user.id,
        target_type="user",
        target_id=str(user.id),
    )
    db.commit()
    return issued


def request_password_reset(
    db: Session, settings: Settings, *, email: str, ip_key: str, now: datetime
) -> OutgoingEmail | None:
    """AUTH-006. Identical outcome for every email: limits are keyed on the submitted
    address, and only an existing ACTIVE account gets a (background) email."""
    email = normalize_email(email)
    ratelimit.consume(db, RESET_IP, ip_key, now)
    ratelimit.consume(db, RESET_EMAIL, ratelimit.hashed_key(email), now)
    user = _find_user(db, email)
    if user is None or not can_sign_in(user):
        return None
    token = issue_token(db, user.id, TokenPurpose.RESET_PASSWORD, RESET_TOKEN_TTL, now)
    db.commit()
    return _reset_email(settings, user, token)


def confirm_password_reset(
    db: Session, *, token: str, new_password: str, ip_key: str, now: datetime
) -> None:
    """AUTH-006. Does not verify the email and does not sign anyone in; ends all sessions."""
    ratelimit.consume(db, TOKEN_ATTEMPTS_IP, ip_key, now)
    digest = token_digest(token)
    row = db.execute(
        select(UserToken, User)
        .join(User, User.id == UserToken.user_id)
        .where(UserToken.token_hash == digest, UserToken.purpose == TokenPurpose.RESET_PASSWORD)
    ).first()
    if row is None:
        raise _token_error(db, digest, TokenPurpose.RESET_PASSWORD, now)
    token_row, user = row
    if token_row.used_at is not None or token_row.expires_at <= now:
        raise _token_error(db, digest, TokenPurpose.RESET_PASSWORD, now)
    if not can_sign_in(user):  # suspended or deactivated accounts cannot reset
        raise BadRequest("This link isn't valid.", code="token_invalid")

    # Validate before consuming, so a weak password doesn't burn the user's only link.
    _check_new_password(new_password, user.email, "new_password")
    if _consume_token(db, digest, TokenPurpose.RESET_PASSWORD, now) is None:
        raise _token_error(db, digest, TokenPurpose.RESET_PASSWORD, now)  # lost a race

    user.password_hash = hash_password(new_password)
    sessions.revoke_all_sessions(db, user.id)
    db.execute(
        delete(UserToken).where(
            UserToken.user_id == user.id,
            UserToken.purpose == TokenPurpose.RESET_PASSWORD,
            UserToken.used_at.is_(None),
        )
    )
    record_audit(
        db,
        action=ACTION_PASSWORD_RESET,
        target_type="user",
        target_id=str(user.id),
    )
    db.commit()


def sign_out(db: Session, *, session: AuthSession) -> None:
    sessions.revoke_session(db, session.id_hash)
    db.commit()


def sign_out_everywhere(db: Session, *, user: User) -> None:
    sessions.revoke_all_sessions(db, user.id)
    db.commit()
