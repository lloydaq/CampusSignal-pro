"""Platform administration decisions (ADMIN-001…004, P-7, ADMIN-008). Pure functions."""

from app.models import College, CollegeStatus
from app.models.user import PlatformRole, User, UserStatus

# ADMIN-001: ONBOARDING -> ACTIVE <-> SUSPENDED. A college never goes back to ONBOARDING.
COLLEGE_TRANSITIONS: dict[str, frozenset[str]] = {
    CollegeStatus.ONBOARDING: frozenset({CollegeStatus.ACTIVE}),
    CollegeStatus.ACTIVE: frozenset({CollegeStatus.SUSPENDED}),
    CollegeStatus.SUSPENDED: frozenset({CollegeStatus.ACTIVE}),
}

PLATFORM_ADMIN_CANNOT_JOIN = "platform_admin_cannot_join"
INVITE_EMAIL_MISMATCH = "invite_email_mismatch"
COLLEGE_INACTIVE = "college_inactive"


def is_platform_admin(user: User) -> bool:
    return user.platform_role == PlatformRole.PLATFORM_ADMIN


def can_change_college_status(current: str, target: str) -> bool:
    return target in COLLEGE_TRANSITIONS.get(current, frozenset())


def college_status_change_needs_reason(target: str) -> bool:
    return target == CollegeStatus.SUSPENDED


def can_suspend_user(actor: User, target: User) -> bool:
    """ADMIN-004. Not oneself (a platform could lock out its last operator)."""
    return actor.id != target.id and target.status == UserStatus.ACTIVE


def can_unsuspend_user(target: User) -> bool:
    return target.status == UserStatus.SUSPENDED


def invite_acceptance_problem(user: User, invite_email: str, college: College) -> str | None:
    """Why `user` may not accept an invite for `invite_email` to `college` (403 code), or None.

    - P-7: a PLATFORM_ADMIN account never holds a college membership.
    - The invite is bound to its email (MEMBER-007); being signed in as that address is what
      proves the person controls it (decided 2026-10-23), and is why acceptance may then mark
      the email verified.
    - A SUSPENDED college can't be joined; an ONBOARDING one can (its first admin sets it up).
    """
    if is_platform_admin(user):
        return PLATFORM_ADMIN_CANNOT_JOIN
    if user.email.lower() != invite_email.lower():
        return INVITE_EMAIL_MISMATCH
    if college.status == CollegeStatus.SUSPENDED:
        return COLLEGE_INACTIVE
    return None
