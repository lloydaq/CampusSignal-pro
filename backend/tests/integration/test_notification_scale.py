"""Fan-out size (Phases.md Phase 4 risk): an URGENT college notice notifies every ACTIVE member
in one INSERT … SELECT. This measures it with 20,000 synthetic members, the size the design
allows for (architecture.md §15). The limit is generous so a slow CI runner doesn't flake; the
point is to catch a change that makes the fan-out per-row."""

import time

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import (
    College,
    CollegeMembership,
    CollegeStatus,
    MembershipKind,
    MembershipStatus,
    Notice,
    NoticeStatus,
    User,
)
from app.models.notification import Notification
from app.services import notifications
from tests.integration.conftest import Clock

pytestmark = pytest.mark.integration

MEMBERS = 20_000
LIMIT_SECONDS = 15.0


def test_twenty_thousand_members_are_notified_in_one_statement(
    session: Session, clock: Clock, capsys: pytest.CaptureFixture[str]
) -> None:
    college = College(
        name="Scale College", slug="scale", timezone="UTC", status=CollegeStatus.ACTIVE
    )
    session.add(college)
    session.flush()
    session.execute(
        text(
            "INSERT INTO users (email, password_hash, display_name, email_verified_at) "
            "SELECT 'scale-' || g || '@northfield.example', 'x', 'Scale ' || g, now() "
            "FROM generate_series(1, :n) g"
        ),
        {"n": MEMBERS},
    )
    session.execute(
        text(
            "INSERT INTO college_memberships (user_id, college_id, kind, status) "
            "SELECT id, :c, :kind, :status FROM users WHERE email LIKE 'scale-%@northfield.example'"
        ),
        {"c": college.id, "kind": MembershipKind.STUDENT, "status": MembershipStatus.ACTIVE},
    )
    author = session.execute(
        select(CollegeMembership).where(CollegeMembership.college_id == college.id).limit(1)
    ).scalar_one()
    notice = Notice(
        college_id=college.id,
        author_membership_id=author.id,
        title="Scale test",
        body="x",
        category="GENERAL",
        priority="URGENT",
        scope="COLLEGE",
        status=NoticeStatus.PUBLISHED,
        published_at=clock.now,
    )
    session.add(notice)
    session.flush()
    assert session.execute(select(func.count()).select_from(User)).scalar_one() >= MEMBERS

    started = time.perf_counter()
    created = notifications.notify_notice_published(session, notice, clock.now)
    elapsed = time.perf_counter() - started

    assert created == MEMBERS
    assert session.execute(select(func.count()).select_from(Notification)).scalar_one() == MEMBERS
    with capsys.disabled():
        print(f"\nfan-out of {created} notifications took {elapsed:.2f} s")
    assert elapsed < LIMIT_SECONDS
