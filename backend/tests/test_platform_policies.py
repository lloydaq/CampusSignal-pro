"""Platform policies as pure functions (ADMIN-001/004, P-7, MEMBER-007)."""

import uuid

import pytest

from app.models import College, CollegeStatus
from app.models.user import PlatformRole, User, UserStatus
from app.policies.platform import (
    can_change_college_status,
    can_suspend_user,
    can_unsuspend_user,
    college_status_change_needs_reason,
    invite_acceptance_problem,
    is_platform_admin,
)


def user(
    email: str = "a@northfield.example",
    *,
    admin: bool = False,
    status: UserStatus = UserStatus.ACTIVE,
) -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash="x",
        display_name="A",
        status=status,
        platform_role=PlatformRole.PLATFORM_ADMIN if admin else None,
    )


def college(status: CollegeStatus) -> College:
    return College(name="Northfield Institute", slug="northfield", timezone="UTC", status=status)


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        ("ONBOARDING", "ACTIVE", True),
        ("ONBOARDING", "SUSPENDED", False),
        ("ACTIVE", "SUSPENDED", True),
        ("ACTIVE", "ONBOARDING", False),
        ("SUSPENDED", "ACTIVE", True),
        ("SUSPENDED", "ONBOARDING", False),
    ],
)
def test_college_lifecycle(current: str, target: str, allowed: bool) -> None:
    assert can_change_college_status(current, target) is allowed


def test_only_suspension_needs_a_reason() -> None:
    assert college_status_change_needs_reason("SUSPENDED")
    assert not college_status_change_needs_reason("ACTIVE")


def test_user_suspension_rules() -> None:
    admin = user(admin=True)
    assert is_platform_admin(admin) and not is_platform_admin(user())
    assert can_suspend_user(admin, user())
    assert not can_suspend_user(admin, admin)
    assert not can_suspend_user(admin, user(status=UserStatus.SUSPENDED))
    assert can_unsuspend_user(user(status=UserStatus.SUSPENDED))
    assert not can_unsuspend_user(user(status=UserStatus.DEACTIVATED))


@pytest.mark.parametrize(
    ("who", "invited", "college_status", "problem"),
    [
        (user("a@northfield.example"), "A@Northfield.example", CollegeStatus.ONBOARDING, None),
        (user("a@northfield.example"), "a@northfield.example", CollegeStatus.ACTIVE, None),
        (
            user("b@northfield.example"),
            "a@northfield.example",
            CollegeStatus.ACTIVE,
            "invite_email_mismatch",
        ),
        (
            user("a@northfield.example", admin=True),
            "a@northfield.example",
            CollegeStatus.ACTIVE,
            "platform_admin_cannot_join",
        ),
        (
            user("a@northfield.example"),
            "a@northfield.example",
            CollegeStatus.SUSPENDED,
            "college_inactive",
        ),
    ],
)
def test_invite_acceptance(
    who: User, invited: str, college_status: CollegeStatus, problem: str | None
) -> None:
    assert invite_acceptance_problem(who, invited, college(college_status)) == problem
