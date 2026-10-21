"""Password hashing, password policy and tokens (AUTH-002, AUTH-003, AUTH-006). No database."""

import hashlib

import pytest
from argon2 import PasswordHasher

from app.core.security import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    burn_password_check,
    common_passwords,
    hash_password,
    new_token,
    password_needs_rehash,
    password_problem,
    token_digest,
    verify_password,
)


def test_hash_is_argon2id_with_pinned_parameters() -> None:
    encoded = hash_password("a perfectly fine passphrase")
    assert encoded.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert not password_needs_rehash(encoded)


def test_hash_never_contains_the_password_and_is_salted() -> None:
    first, second = hash_password("same secret phrase"), hash_password("same secret phrase")
    assert "same secret phrase" not in first
    assert first != second


def test_verify_accepts_correct_and_rejects_wrong_or_malformed() -> None:
    encoded = hash_password("correct horse battery")
    assert verify_password(encoded, "correct horse battery")
    assert not verify_password(encoded, "Correct horse battery")
    assert not verify_password("not-a-hash", "correct horse battery")


def test_weaker_parameters_need_rehash() -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8 * 1024).hash("legacy password here")
    assert password_needs_rehash(weak)


def test_burn_password_check_runs_without_error() -> None:
    burn_password_check("whatever the user typed")


@pytest.mark.parametrize("password", ["password1234", "PASSWORD1234", "Password1234", "1234567890"])
def test_common_passwords_rejected_case_insensitively(password: str) -> None:
    # US-01: "password1234" is rejected with a field-level error.
    assert password_problem(password) == (
        "This password is too common. Choose one that's harder to guess."
    )


def test_common_list_is_loaded_and_only_holds_long_entries() -> None:
    words = common_passwords()
    assert len(words) > 100_000
    assert all(len(w) >= PASSWORD_MIN_LENGTH for w in words)
    assert all(w == w.lower() for w in list(words)[:1000])


def test_length_limits() -> None:
    assert password_problem("x" * (PASSWORD_MIN_LENGTH - 1)) == "Use at least 10 characters."
    assert (
        password_problem("Zq8!" + "x" * (PASSWORD_MAX_LENGTH - 3)) == "Use at most 128 characters."
    )
    assert password_problem("tidal-quartz-lantern") is None


def test_password_built_from_email_is_rejected() -> None:
    assert password_problem("meera.rao2026!", email="Meera.Rao@northfield.example") == (
        "Don't use your email address in your password."
    )
    # Very short local parts are not treated as identifying.
    assert password_problem("ab-quartz-lantern", email="ab@northfield.example") is None


def test_tokens_are_256_bit_urlsafe_and_only_digest_is_kept() -> None:
    token, digest = new_token()
    assert len(token) >= 43  # 32 random bytes, base64url
    assert set(token) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert digest == hashlib.sha256(token.encode()).digest()
    assert len(digest) == 32
    assert token_digest(token) == digest
    assert new_token()[0] != token
