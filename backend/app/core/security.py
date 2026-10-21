"""Password hashing, password policy and one-time tokens (PRD AUTH-002/003/006, Rules R-2.9).

Passwords are hashed with Argon2id; parameters are pinned here (not left to library
defaults) so an upgrade cannot silently weaken them. Tokens (sessions, email links) are
random 256-bit values; only their SHA-256 digest is ever stored.
"""

import gzip
import hashlib
import secrets
from functools import lru_cache
from importlib import resources

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

# RFC 9106 second recommended option (64 MiB, t=3, p=4); above architecture.md §10's
# floor of 19 MiB / t=2.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

TOKEN_BYTES = 32  # 256 bits of entropy


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@lru_cache
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    """Spend the same time as a real verification, for unknown accounts (no timing oracle)."""
    verify_password(_dummy_hash(), password)


@lru_cache
def common_passwords() -> frozenset[str]:
    """Lower-cased common passwords of 10+ characters (see app/core/data/README.md)."""
    data = resources.files("app.core").joinpath("data/common-passwords.txt.gz").read_bytes()
    return frozenset(gzip.decompress(data).decode("utf-8").splitlines())


def password_problem(password: str, *, email: str = "") -> str | None:
    """A user-facing reason the password is not acceptable, or None if it is."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Use at least {PASSWORD_MIN_LENGTH} characters."
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"Use at most {PASSWORD_MAX_LENGTH} characters."
    lowered = password.lower()
    if lowered in common_passwords():
        return "This password is too common. Choose one that's harder to guess."
    local_part = email.split("@", 1)[0].lower()
    if len(local_part) >= 4 and local_part in lowered:
        return "Don't use your email address in your password."
    return None


def new_token() -> tuple[str, bytes]:
    """A random URL-safe token for the user and the digest to store in its place."""
    token = secrets.token_urlsafe(TOKEN_BYTES)
    return token, token_digest(token)


def token_digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()
