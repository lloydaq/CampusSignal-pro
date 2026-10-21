"""Request validation for the auth routes (Rules R-2.7). No database."""

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    VerifyEmailRequest,
)

GOOD = {
    "email": "aarav@northfield.example",
    "password": "tidal-quartz-lantern",
    "display_name": "Aarav",
}


def _messages(exc: pytest.ExceptionInfo[ValidationError]) -> dict[str, str]:
    return {".".join(map(str, e["loc"])): e["msg"] for e in exc.value.errors()}


def test_valid_registration() -> None:
    body = RegisterRequest.model_validate(GOOD)
    assert body.email == "aarav@northfield.example"
    assert body.display_name == "Aarav"


@pytest.mark.parametrize("email", ["  Aarav@Northfield.EXAMPLE ", "AARAV@northfield.example\n"])
def test_email_is_trimmed_and_lowercased(email: str) -> None:
    body = LoginRequest.model_validate({"email": email, "password": "x"})
    assert body.email == "aarav@northfield.example"


@pytest.mark.parametrize(
    "email",
    [
        "",
        "aarav",
        "aarav@",
        "@northfield.example",
        "a b@northfield.example",
        "a@b",
        "a@b.c",
        "a@@b.example",
        "a\x00@b.example",
        "x" * 250 + "@b.example",
    ],
)
def test_bad_emails_are_rejected_with_a_readable_message(email: str) -> None:
    with pytest.raises(ValidationError) as exc:
        PasswordResetRequest.model_validate({"email": email})
    assert _messages(exc) == {"email": "Enter a valid email address."}


def test_display_name_whitespace_is_collapsed() -> None:
    body = RegisterRequest.model_validate({**GOOD, "display_name": "  Aarav \n  Nair  "})
    assert body.display_name == "Aarav Nair"


@pytest.mark.parametrize("name", ["", "   ", "\n\t", "x" * 61, "bad\x00name"])
def test_bad_display_names(name: str) -> None:
    with pytest.raises(ValidationError) as exc:
        RegisterRequest.model_validate({**GOOD, "display_name": name})
    assert _messages(exc) == {"display_name": "Use 1 to 60 characters for your name."}


def test_display_name_at_the_limit_is_accepted() -> None:
    assert (
        RegisterRequest.model_validate({**GOOD, "display_name": "x" * 60}).display_name == "x" * 60
    )


def test_password_length_is_capped_before_hashing() -> None:
    RegisterRequest.model_validate({**GOOD, "password": "x" * 128})
    with pytest.raises(ValidationError) as exc:
        RegisterRequest.model_validate({**GOOD, "password": "x" * 129})
    assert "password" in _messages(exc)
    with pytest.raises(ValidationError):
        LoginRequest.model_validate({"email": GOOD["email"], "password": ""})


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (RegisterRequest, {**GOOD, "college_id": "x"}),
        (RegisterRequest, {**GOOD, "platform_role": "PLATFORM_ADMIN"}),
        (RegisterRequest, {**GOOD, "status": "ACTIVE"}),
        (RegisterRequest, {**GOOD, "email_verified": True}),
        (LoginRequest, {"email": GOOD["email"], "password": "x", "remember": True}),
        (VerifyEmailRequest, {"token": "t", "user_id": "x"}),
        (PasswordResetRequest, {"email": GOOD["email"], "extra": 1}),
        (PasswordResetConfirmRequest, {"token": "t", "new_password": "x", "email": "a@b.example"}),
        (ChangePasswordRequest, {"current_password": "a", "new_password": "b", "user_id": "x"}),
    ],
)
def test_unknown_fields_are_rejected_not_ignored(
    model: type[BaseModel], payload: dict[str, object]
) -> None:
    # Mass-assignment guard: clients can't set roles, status, verification or ownership.
    with pytest.raises(ValidationError) as exc:
        model.model_validate(payload)
    assert any(e["type"] == "extra_forbidden" for e in exc.value.errors())


@pytest.mark.parametrize("token", ["", "x" * 201])
def test_token_length_bounds(token: str) -> None:
    with pytest.raises(ValidationError):
        VerifyEmailRequest.model_validate({"token": token})
