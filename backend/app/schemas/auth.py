"""Request and response models for authentication (Rules R-2.7: unknown fields rejected,
explicit limits, responses whitelist their fields)."""

import re
import uuid
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from pydantic_core import PydanticCustomError

from app.models.user import User

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
EMAIL_MAX_LENGTH = 254
DISPLAY_NAME_MAX_LENGTH = 60


def _clean_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > EMAIL_MAX_LENGTH or not value.isprintable() or not _EMAIL.match(value):
        raise PydanticCustomError("invalid_email", "Enter a valid email address.")
    return value


def _clean_display_name(value: str) -> str:
    value = " ".join(value.split())  # trims and collapses whitespace, including newlines
    if not 1 <= len(value) <= DISPLAY_NAME_MAX_LENGTH or not value.isprintable():
        raise PydanticCustomError("invalid_display_name", "Use 1 to 60 characters for your name.")
    return value


Email = Annotated[str, AfterValidator(_clean_email)]
DisplayName = Annotated[str, AfterValidator(_clean_display_name)]
# Passwords are length-capped before hashing so a huge body can't make hashing expensive;
# the real rules (minimum length, common passwords) are reported by the service.
Password = Annotated[str, Field(min_length=1, max_length=128)]
OneTimeToken = Annotated[str, Field(min_length=1, max_length=200)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(_Request):
    email: Email
    password: Password
    display_name: DisplayName


class LoginRequest(_Request):
    email: Email
    password: Password


class VerifyEmailRequest(_Request):
    token: OneTimeToken


class PasswordResetRequest(_Request):
    email: Email


class PasswordResetConfirmRequest(_Request):
    token: OneTimeToken
    new_password: Password


class ChangePasswordRequest(_Request):
    current_password: Password
    new_password: Password


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    email_verified: bool
    platform_role: str | None

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            email_verified=user.email_verified_at is not None,
            platform_role=user.platform_role,
        )


class MessageResponse(BaseModel):
    message: str


class MeResponse(BaseModel):
    user: UserOut


class LoginResponse(BaseModel):
    user: UserOut
    csrf_token: str


class CsrfResponse(BaseModel):
    csrf_token: str | None


class PasswordChangedResponse(BaseModel):
    csrf_token: str
