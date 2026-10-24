"""Notification policies as pure functions (NOTIF-001, NOTICE-007): no database."""

import uuid

import pytest

from app.models import CollegeMembership, MembershipStatus, Notice, NoticePriority, NoticeScope
from app.models.notification import Notification
from app.policies.notifications import (
    can_read_notification,
    current_college_id,
    notice_notifies_members,
)

ME, OTHER = uuid.uuid4(), uuid.uuid4()
NORTH, RIVER = uuid.uuid4(), uuid.uuid4()


def row(user: uuid.UUID = ME, college: uuid.UUID | None = NORTH) -> Notification:
    return Notification(user_id=user, college_id=college, type="NOTICE_PUBLISHED", title="t")


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (MembershipStatus.ACTIVE, NORTH),
        (MembershipStatus.SUSPENDED, None),  # a suspended member sees no college notifications
        (MembershipStatus.PENDING, None),
        (MembershipStatus.ENDED, None),
    ],
)
def test_only_an_active_membership_names_the_current_college(
    status: MembershipStatus, expected: uuid.UUID | None
) -> None:
    membership = CollegeMembership(college_id=NORTH, status=status)
    assert current_college_id(membership) == expected


def test_no_membership_means_no_current_college() -> None:
    assert current_college_id(None) is None


@pytest.mark.parametrize(
    ("owner", "college", "current", "allowed"),
    [
        (ME, NORTH, NORTH, True),
        (ME, None, NORTH, True),  # college-less notifications follow the person
        (ME, None, None, True),
        (ME, NORTH, None, False),  # no longer an active member there
        (ME, RIVER, NORTH, False),  # another college's notification after moving
        (OTHER, NORTH, NORTH, False),  # somebody else's
        (OTHER, None, None, False),
    ],
)
def test_who_may_read_a_notification(
    owner: uuid.UUID, college: uuid.UUID | None, current: uuid.UUID | None, allowed: bool
) -> None:
    assert can_read_notification(ME, current, row(owner, college)) is allowed


@pytest.mark.parametrize(
    ("priority", "notifies"),
    [(NoticePriority.NORMAL, False), (NoticePriority.HIGH, True), (NoticePriority.URGENT, True)],
)
def test_only_high_and_urgent_notices_notify(priority: NoticePriority, notifies: bool) -> None:
    notice = Notice(priority=priority, scope=NoticeScope.COLLEGE)
    assert notice_notifies_members(notice) is notifies
