"""Platform-admin accounts (PRD ADMIN-005, P-7, ADR-13).

Created only by the operator CLI, never through the API. A platform admin is always a new,
separate account: an existing email is refused rather than promoted, so a person's college
identity and their platform role never share an account.
"""

from dataclasses import dataclass
from datetime import datetime

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, ValidationFailed
from app.core.security import hash_password, password_problem
from app.models.user import PlatformRole, User
from app.schemas.auth import DisplayName, Email
from app.services.audit import record_audit

ACTION_PLATFORM_ADMIN_CREATED = "platform.admin_created"

_EMAIL = TypeAdapter(Email)
_DISPLAY_NAME = TypeAdapter(DisplayName)


@dataclass(frozen=True)
class AdminIdentity:
    email: str
    display_name: str


def _clean(adapter: TypeAdapter[str], value: str, field: str) -> str:
    try:
        return adapter.validate_python(value)
    except ValidationError as exc:
        raise ValidationFailed.field(field, exc.errors()[0]["msg"]) from None


def clean_identity(*, email: str, display_name: str) -> AdminIdentity:
    """Validate the inputs with the same rules as registration (no database access)."""
    return AdminIdentity(
        email=_clean(_EMAIL, email, "email"),
        display_name=_clean(_DISPLAY_NAME, display_name, "display_name"),
    )


def create_platform_admin(
    db: Session, *, email: str, display_name: str, password: str, now: datetime
) -> User:
    """Create a verified PLATFORM_ADMIN account and audit it, in one transaction."""
    identity = clean_identity(email=email, display_name=display_name)
    problem = password_problem(password, email=identity.email)
    if problem is not None:
        raise ValidationFailed.field("password", problem)

    user = User(
        email=identity.email,
        password_hash=hash_password(password),
        display_name=identity.display_name,
        platform_role=PlatformRole.PLATFORM_ADMIN,
        # The operator vouches for the address; there is no verification email to click.
        email_verified_at=now,
    )
    try:
        with db.begin_nested():
            db.add(user)
            db.flush()
    except IntegrityError:
        db.rollback()
        raise Conflict("An account with this email already exists.") from None
    record_audit(
        db,
        action=ACTION_PLATFORM_ADMIN_CREATED,
        target_type="user",
        target_id=str(user.id),
        metadata={"via": "cli"},
    )
    db.commit()
    return user
