"""Two posts sent at once by a member at their hourly limit: the member's row lock lets exactly
one through (COMMUNITY-008). Two reactions sent at once leave one row (COMMUNITY-004).
Independent connections and committed rows, cleaned up afterwards (see test_notice_concurrency).
"""

import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import RateLimited
from app.models import (
    College,
    CollegeMembership,
    CollegeStatus,
    MembershipKind,
    MembershipStatus,
    Post,
    PostVisibility,
    Reaction,
)
from app.models.user import User
from app.policies.campus import CampusContext
from app.services import community

pytestmark = pytest.mark.integration

RACE = "college_id IN (SELECT id FROM colleges WHERE slug LIKE 'race-%')"


@pytest.fixture
def factory(config: Config, test_database_url: str) -> Iterator[sessionmaker[Session]]:
    command.upgrade(config, "head")
    engine = create_engine(test_database_url, pool_size=4, hide_parameters=True)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        with engine.begin() as conn:
            for table in ("reactions", "comments", "posts", "college_memberships"):
                conn.execute(text(f"DELETE FROM {table} WHERE {RACE}"))  # noqa: S608 - constants
            conn.execute(text("DELETE FROM colleges WHERE slug LIKE 'race-%'"))
            conn.execute(text("DELETE FROM users WHERE email LIKE 'race-%@northfield.example'"))
        engine.dispose()


def _setup(factory: sessionmaker[Session], existing_posts: int) -> CampusContext:
    """A college with one member who has already posted `existing_posts` times this hour."""
    tag = uuid.uuid4().hex[:10]
    now = datetime.now(UTC)
    with factory() as db:
        college = College(
            name="Race College", slug=f"race-{tag}", timezone="UTC", status=CollegeStatus.ACTIVE
        )
        db.add(college)
        db.flush()
        user = User(email=f"race-{tag}@northfield.example", password_hash="x", display_name="R")
        db.add(user)
        db.flush()
        membership = CollegeMembership(
            user_id=user.id,
            college_id=college.id,
            kind=MembershipKind.STUDENT,
            status=MembershipStatus.ACTIVE,
        )
        db.add(membership)
        db.flush()
        for n in range(existing_posts):
            db.add(
                Post(
                    college_id=college.id,
                    author_membership_id=membership.id,
                    visibility=PostVisibility.COLLEGE,
                    body=f"Post {n}",
                    created_at=now - timedelta(minutes=30),
                )
            )
        db.commit()
        return CampusContext(user=user, membership=membership, college=college, grants=())


def _race(factory: sessionmaker[Session], act: Callable[[Session], None]) -> Counter[str]:
    barrier = threading.Barrier(2)

    def run(_: int) -> str:
        barrier.wait(timeout=30)
        with factory() as db:
            try:
                act(db)
            except RateLimited:
                return "rate_limited"
            return "ok"

    with ThreadPoolExecutor(max_workers=2) as pool:
        return Counter(pool.map(run, range(2)))


@pytest.fixture
def slow_limit_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pause just after counting: without the member's row lock, both requests would count
    the same nine posts and both get through."""
    original = community._check_hourly_limit

    def counted_then_paused(*args: Any) -> None:
        original(*args)
        time.sleep(0.3)

    monkeypatch.setattr(community, "_check_hourly_limit", counted_then_paused)


@pytest.mark.parametrize("round_", range(2))
def test_the_tenth_post_goes_through_once(
    factory: sessionmaker[Session], slow_limit_check: None, round_: int
) -> None:
    campus = _setup(factory, existing_posts=9)

    def act(db: Session) -> None:
        community.create_post(
            db, campus, body="Last one", visibility=PostVisibility.COLLEGE, now=datetime.now(UTC)
        )

    assert _race(factory, act) == {"ok": 1, "rate_limited": 1}
    with factory() as db:
        count = db.execute(
            select(func.count()).select_from(Post).where(Post.college_id == campus.college_id)
        ).scalar_one()
    assert count == 10


def test_two_reactions_at_once_leave_one(factory: sessionmaker[Session]) -> None:
    campus = _setup(factory, existing_posts=1)
    with factory() as db:
        post_id = db.execute(
            select(Post.id).where(Post.college_id == campus.college_id)
        ).scalar_one()

    def act(db: Session) -> None:
        community.react(db, campus, post_id, now=datetime.now(UTC))

    assert _race(factory, act) == {"ok": 2}
    with factory() as db:
        count = db.execute(
            select(func.count()).select_from(Reaction).where(Reaction.post_id == post_id)
        ).scalar_one()
    assert count == 1
