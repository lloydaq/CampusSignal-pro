"""SQLAlchemy models. Importing this package registers every table on Base.metadata,
which Alembic (alembic/env.py) compares against the migrations."""

from app.models.audit import AuditLog
from app.models.auth_session import AuthSession
from app.models.college import (
    College,
    CollegeMembership,
    CollegeStatus,
    Department,
    Invite,
    MembershipKind,
    MembershipStatus,
    Role,
    RoleGrant,
    RosterEntry,
    VerificationFlag,
)
from app.models.rate_limit import RateLimitCounter
from app.models.user import PlatformRole, User, UserStatus
from app.models.user_token import TokenPurpose, UserToken

__all__ = [
    "AuditLog",
    "AuthSession",
    "College",
    "CollegeMembership",
    "CollegeStatus",
    "Department",
    "Invite",
    "MembershipKind",
    "MembershipStatus",
    "PlatformRole",
    "RateLimitCounter",
    "Role",
    "RoleGrant",
    "RosterEntry",
    "TokenPurpose",
    "User",
    "UserStatus",
    "UserToken",
    "VerificationFlag",
]
