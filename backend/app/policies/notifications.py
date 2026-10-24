"""Notification decisions (NOTIF-001, NOTICE-007). Pure functions over loaded rows.

A notification is its owner's alone, and only the ones that follow the person (no college) or
belong to their *current* ACTIVE membership's college are listed, counted or openable: after
moving colleges, the old college's notifications are gone from view (NOTIF-001). Lists and
counts filter in SQL with `current_college_id`; `can_read_notification` is the same rule for
one row, and a test keeps them in agreement.
"""

import uuid

from app.models import CollegeMembership, MembershipStatus, Notice, NoticePriority
from app.models.notification import Notification


def current_college_id(membership: CollegeMembership | None) -> uuid.UUID | None:
    """The college whose notifications the user may see: that of their ACTIVE membership."""
    if membership is not None and membership.status == MembershipStatus.ACTIVE:
        return membership.college_id
    return None


def can_read_notification(
    user_id: uuid.UUID, current_college: uuid.UUID | None, notification: Notification
) -> bool:
    if notification.user_id != user_id:
        return False
    return notification.college_id is None or notification.college_id == current_college


def notice_notifies_members(notice: Notice) -> bool:
    """NOTICE-007: HIGH and URGENT notices notify the members in their scope."""
    return notice.priority in (NoticePriority.HIGH, NoticePriority.URGENT)
