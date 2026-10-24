"""Student membership requests and their review (MEMBER-002…006, P-7). Pure functions."""

from dataclasses import dataclass

from app.models import CollegeMembership, RosterEntry, VerificationFlag
from app.models.user import User
from app.policies.campus import CampusContext, administered_departments, is_college_admin
from app.policies.platform import PLATFORM_ADMIN_CANNOT_JOIN, is_platform_admin

EMAIL_UNVERIFIED = "email_unverified"


def request_problem(user: User) -> str | None:
    """Why `user` may not ask to join a college (403 code), or None. A verified email is
    mandatory before any membership exists (architecture.md §10, security review W1)."""
    if is_platform_admin(user):
        return PLATFORM_ADMIN_CANNOT_JOIN
    if user.email_verified_at is None:
        return EMAIL_UNVERIFIED
    return None


@dataclass(frozen=True)
class Outcome:
    activate: bool
    flag: VerificationFlag | None


def classify_request(user: User, entry: RosterEntry | None, entry_claimed: bool) -> Outcome:
    """MEMBER-003/004: activate only when the roll number matches an unclaimed roster entry
    whose email is the user's verified email; otherwise record why, for approvers only."""
    if entry is None:
        return Outcome(False, VerificationFlag.NO_ROSTER_MATCH)
    if entry_claimed:
        return Outcome(False, VerificationFlag.ROSTER_CLAIMED)
    if entry.email is None:
        return Outcome(False, VerificationFlag.NO_ROSTER_EMAIL)
    if entry.email.lower() != user.email.lower():
        return Outcome(False, VerificationFlag.EMAIL_MISMATCH)
    return Outcome(True, None)


def can_review_request(campus: CampusContext, request: CollegeMembership) -> bool:
    """MEMBER-004/006, US-03: college admins review everything; department admins review
    requests whose roster entry is in a department they administer. NO_ROSTER_MATCH requests
    (no department) are for college admins only."""
    if is_college_admin(campus.grants):
        return True
    if request.verification_flag == VerificationFlag.NO_ROSTER_MATCH:
        return False
    return request.department_id in administered_departments(campus.grants)
