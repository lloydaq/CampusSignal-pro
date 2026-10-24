"""Two people changing the same notice at the same moment: the row lock lets exactly one win.

Publishing twice must publish once, and two edits made from the same version must not both
apply (NOTICE-003, 006; architecture.md §11.1 "409 version"). Independent connections and
committed rows, cleaned up afterwards (see test_last_admin_concurrency).
"""

import threading
import time
import uuid
from collections import Counter
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import Conflict
from app.models import (
    College,
    CollegeMembership,
    CollegeStatus,
    MembershipKind,
    MembershipStatus,
    Notice,
    NoticeStatus,
    Role,
    RoleGrant,
)
from app.models.user import User
from app.policies.campus import CampusContext
from app.services import notices

pytestmark = pytest.mark.integration


@pytest.fixture
def factory(config: Config, test_database_url: str) -> Iterator[sessionmaker[Session]]:
    command.upgrade(config, "head")
    engine = create_engine(test_database_url, pool_size=4, hide_parameters=True)
    started = datetime.now(UTC)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL campussignal.audit_purge = 'on'"))
            conn.execute(text("DELETE FROM audit_log WHERE created_at >= :t"), {"t": started})
            race = "college_id IN (SELECT id FROM colleges WHERE slug LIKE 'race-%')"
            for table in ("notices", "role_grants", "college_memberships"):
                conn.execute(text(f"DELETE FROM {table} WHERE {race}"))  # noqa: S608 - constants
            conn.execute(text("DELETE FROM colleges WHERE slug LIKE 'race-%'"))
            conn.execute(text("DELETE FROM users WHERE email LIKE 'race-%@northfield.example'"))
        engine.dispose()


def _setup(
    factory: sessionmaker[Session],
) -> tuple[College, list[tuple[User, CollegeMembership, RoleGrant]], uuid.UUID]:
    """A college with two college admins and one draft notice."""
    tag = uuid.uuid4().hex[:10]
    with factory() as db:
        college = College(
            name="Race College", slug=f"race-{tag}", timezone="UTC", status=CollegeStatus.ACTIVE
        )
        db.add(college)
        db.flush()
        admins = []
        for n in range(2):
            user = User(
                email=f"race-{n}-{tag}@northfield.example",
                password_hash="x",
                display_name=f"Admin {n}",
            )
            db.add(user)
            db.flush()
            membership = CollegeMembership(
                user_id=user.id,
                college_id=college.id,
                kind=MembershipKind.STAFF,
                status=MembershipStatus.ACTIVE,
            )
            db.add(membership)
            db.flush()
            grant = RoleGrant(
                college_id=college.id, membership_id=membership.id, role=Role.COLLEGE_ADMIN
            )
            db.add(grant)
            db.flush()
            admins.append((user, membership, grant))
        notice = Notice(
            college_id=college.id,
            author_membership_id=admins[0][1].id,
            title="Race",
            body="Race",
            category="GENERAL",
            scope="COLLEGE",
            status=NoticeStatus.DRAFT,
        )
        db.add(notice)
        db.commit()
        return college, admins, notice.id


@pytest.fixture
def slow_version_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pause just after the version check: the race lives between that check and the write,
    and this makes both requests reach it together, so a missing row lock always shows."""
    original = notices._check_version

    def checked_then_paused(*args: Any) -> None:
        original(*args)
        time.sleep(0.3)

    monkeypatch.setattr(notices, "_check_version", checked_then_paused)


def _race(
    factory: sessionmaker[Session],
    college: College,
    admins: list[tuple[User, CollegeMembership, RoleGrant]],
    act: Any,
) -> Counter[str]:
    barrier = threading.Barrier(2)

    def run(index: int) -> str:
        user, membership, grant = admins[index]
        barrier.wait(timeout=30)
        with factory() as db:
            campus = CampusContext(
                user=user, membership=membership, college=college, grants=(grant,)
            )
            try:
                act(db, campus, index)
            except Conflict as exc:
                return exc.error_code
            return "ok"

    with ThreadPoolExecutor(max_workers=2) as pool:
        return Counter(pool.map(run, range(2)))


@pytest.mark.parametrize("round_", range(2))
def test_two_simultaneous_publishes_publish_once(
    factory: sessionmaker[Session], slow_version_check: None, round_: int
) -> None:
    college, admins, notice_id = _setup(factory)

    def publish(db: Session, campus: CampusContext, index: int) -> None:
        notices.publish_notice(db, campus, notice_id, version=1, now=datetime.now(UTC))

    outcomes = _race(factory, college, admins, publish)

    assert outcomes == {"ok": 1, "version_conflict": 1}
    with factory() as db:
        published = db.execute(
            select(func.count())
            .select_from(Notice)
            .where(Notice.status == NoticeStatus.PUBLISHED, Notice.id == notice_id)
        ).scalar_one()
        audited = db.execute(
            text(
                "SELECT count(*) FROM audit_log "
                "WHERE action = 'notice.published' AND target_id = :t"
            ),
            {"t": str(notice_id)},
        ).scalar_one()
    assert (published, audited) == (1, 1)


@pytest.mark.parametrize("round_", range(2))
def test_two_edits_from_the_same_version_cannot_both_apply(
    factory: sessionmaker[Session], slow_version_check: None, round_: int
) -> None:
    college, admins, notice_id = _setup(factory)

    def edit(db: Session, campus: CampusContext, index: int) -> None:
        notices.update_notice(
            db,
            campus,
            notice_id,
            version=1,
            changes={"title": f"Edit {index}"},
            now=datetime.now(UTC),
        )

    outcomes = _race(factory, college, admins, edit)

    assert outcomes == {"ok": 1, "version_conflict": 1}
    with factory() as db:
        notice = db.execute(select(Notice).where(Notice.id == notice_id)).scalar_one()
    assert notice.version == 2 and notice.title in {"Edit 0", "Edit 1"}
