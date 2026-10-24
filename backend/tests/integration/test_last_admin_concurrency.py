"""Two college admins removing each other at the same moment must leave one admin
(MEMBER-011, ADMIN-003). The college row lock serialises the two changes.

Independent connections and committed rows, cleaned up afterwards (see test_auth_concurrency).
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
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import Conflict
from app.models import (
    College,
    CollegeMembership,
    CollegeStatus,
    MembershipKind,
    MembershipStatus,
    Role,
    RoleGrant,
)
from app.models.user import User
from app.policies.campus import CampusContext
from app.services import members
from app.services.members import revoke_role, update_member

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
            for table in ("role_grants", "college_memberships"):
                conn.execute(text(f"DELETE FROM {table} WHERE {race}"))  # noqa: S608 - constants
            conn.execute(text("DELETE FROM colleges WHERE slug LIKE 'race-%'"))
            conn.execute(text("DELETE FROM users WHERE email LIKE 'race-%@northfield.example'"))
        engine.dispose()


def _setup(
    factory: sessionmaker[Session],
) -> tuple[College, list[tuple[User, CollegeMembership, RoleGrant]]]:
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
                kind=MembershipKind.FACULTY,
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
        db.commit()
        return college, admins


def _context(
    db: Session, college: College, user: User, membership: CollegeMembership, grant: RoleGrant
) -> CampusContext:
    return CampusContext(user=user, membership=membership, college=college, grants=(grant,))


@pytest.fixture
def slow_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pause after counting the other admins: the race lives between that count and the write,
    and this makes both requests reach it together, so a missing lock always shows."""
    original = members._other_active_admins

    def counted_then_paused(*args: Any) -> int:
        result = original(*args)
        time.sleep(0.3)
        return result

    monkeypatch.setattr(members, "_other_active_admins", counted_then_paused)


@pytest.mark.parametrize("action", ["end", "revoke"])
@pytest.mark.parametrize("round_", range(2))
def test_two_admins_removing_each_other_leave_one(
    factory: sessionmaker[Session], slow_count: None, action: str, round_: int
) -> None:
    college, admins = _setup(factory)
    barrier = threading.Barrier(2)

    def remove_other(index: int) -> str:
        user, membership, grant = admins[index]
        _, other_membership, other_grant = admins[1 - index]
        barrier.wait(timeout=30)
        with factory() as db:
            campus = _context(db, college, user, membership, grant)
            try:
                if action == "end":
                    update_member(
                        db,
                        campus,
                        other_membership.id,
                        department_id=None,
                        status="ENDED",
                        reason="race",
                        now=datetime.now(UTC),
                    )
                else:
                    revoke_role(db, campus, other_membership.id, other_grant.id)
            except Conflict as exc:
                return exc.error_code
            return "ok"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = Counter(pool.map(remove_other, range(2)))
    assert outcomes == {"ok": 1, "last_college_admin": 1}
    with factory() as db:
        remaining = db.execute(
            select(CollegeMembership.id)
            .join(RoleGrant, RoleGrant.membership_id == CollegeMembership.id)
            .where(
                CollegeMembership.college_id == college.id,
                CollegeMembership.status == MembershipStatus.ACTIVE,
                RoleGrant.role == Role.COLLEGE_ADMIN,
            )
        ).all()
    assert len(remaining) == 1
