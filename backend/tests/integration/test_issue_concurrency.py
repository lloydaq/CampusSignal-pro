"""Two coordinators handling the same issue at the same moment: the row lock and the version
let exactly one change apply (architecture.md §11.1 "409 version", Rules R-4.3). Independent
connections and committed rows, cleaned up afterwards (see test_notice_concurrency)."""

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
    CampusIssue,
    College,
    CollegeMembership,
    CollegeStatus,
    IssueStatus,
    IssueUpdate,
    MembershipKind,
    MembershipStatus,
    Role,
    RoleGrant,
)
from app.models.user import User
from app.policies.campus import CampusContext
from app.services.issues import workflow

pytestmark = pytest.mark.integration

RACE = "college_id IN (SELECT id FROM colleges WHERE slug LIKE 'race-%')"


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
            # The timeline is append-only; only this cleanup lifts that, inside its transaction.
            conn.execute(
                text("ALTER TABLE issue_updates DISABLE TRIGGER issue_updates_append_only")
            )
            for table in (
                "notifications",
                "issue_updates",
                "campus_issues",
                "role_grants",
                "college_memberships",
            ):
                conn.execute(text(f"DELETE FROM {table} WHERE {RACE}"))  # noqa: S608 - constants
            conn.execute(text("ALTER TABLE issue_updates ENABLE TRIGGER issue_updates_append_only"))
            conn.execute(text("DELETE FROM colleges WHERE slug LIKE 'race-%'"))
            conn.execute(text("DELETE FROM users WHERE email LIKE 'race-%@northfield.example'"))
        engine.dispose()


def _setup(
    factory: sessionmaker[Session],
) -> tuple[College, list[tuple[User, CollegeMembership, RoleGrant]], uuid.UUID]:
    """A college with two issue coordinators (staff, so either can be assigned) and one
    SUBMITTED issue reported by the first."""
    tag = uuid.uuid4().hex[:10]
    with factory() as db:
        college = College(
            name="Race College", slug=f"race-{tag}", timezone="UTC", status=CollegeStatus.ACTIVE
        )
        db.add(college)
        db.flush()
        coordinators = []
        for n in range(2):
            user = User(
                email=f"race-{n}-{tag}@northfield.example",
                password_hash="x",
                display_name=f"Coordinator {n}",
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
                college_id=college.id, membership_id=membership.id, role=Role.ISSUE_COORDINATOR
            )
            db.add(grant)
            db.flush()
            coordinators.append((user, membership, grant))
        issue = CampusIssue(
            college_id=college.id,
            reporter_membership_id=coordinators[0][1].id,
            category="OTHER",
            title="Race",
            description="Race",
            location_text="Race",
            status=IssueStatus.SUBMITTED,
        )
        db.add(issue)
        db.commit()
        return college, coordinators, issue.id


@pytest.fixture
def slow_version_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pause just after the version check, where a missing row lock would let both through."""
    original = workflow._check_version

    def checked_then_paused(*args: Any) -> None:
        original(*args)
        time.sleep(0.3)

    monkeypatch.setattr(workflow, "_check_version", checked_then_paused)


def _race(
    factory: sessionmaker[Session],
    college: College,
    coordinators: list[tuple[User, CollegeMembership, RoleGrant]],
    act: Any,
) -> Counter[str]:
    barrier = threading.Barrier(2)

    def run(index: int) -> str:
        user, membership, grant = coordinators[index]
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


def _status_rows(factory: sessionmaker[Session], issue_id: uuid.UUID) -> int:
    with factory() as db:
        return db.execute(
            select(func.count())
            .select_from(IssueUpdate)
            .where(IssueUpdate.issue_id == issue_id, IssueUpdate.kind != "CREATED")
        ).scalar_one()


@pytest.mark.parametrize("round_", range(2))
def test_acknowledge_and_reject_at_once_only_one_applies(
    factory: sessionmaker[Session], slow_version_check: None, round_: int
) -> None:
    college, coordinators, issue_id = _setup(factory)

    def act(db: Session, campus: CampusContext, index: int) -> None:
        workflow.transition_issue(
            db,
            campus,
            issue_id,
            to_status=IssueStatus.ACKNOWLEDGED if index == 0 else IssueStatus.REJECTED,
            note=None if index == 0 else "Not ours.",
            duplicate_of_id=None,
            version=1,
            now=datetime.now(UTC),
        )

    assert _race(factory, college, coordinators, act) == {"ok": 1, "version_conflict": 1}
    with factory() as db:
        issue = db.execute(select(CampusIssue).where(CampusIssue.id == issue_id)).scalar_one()
    assert issue.version == 2 and issue.status in {"ACKNOWLEDGED", "REJECTED"}
    assert _status_rows(factory, issue_id) == 1


@pytest.mark.parametrize("round_", range(2))
def test_two_assignments_from_the_same_version_cannot_both_apply(
    factory: sessionmaker[Session], slow_version_check: None, round_: int
) -> None:
    college, coordinators, issue_id = _setup(factory)

    def act(db: Session, campus: CampusContext, index: int) -> None:
        workflow.assign_issue(
            db,
            campus,
            issue_id,
            assignee_id=coordinators[index][1].id,
            version=1,
            now=datetime.now(UTC),
        )

    assert _race(factory, college, coordinators, act) == {"ok": 1, "version_conflict": 1}
    with factory() as db:
        issue = db.execute(select(CampusIssue).where(CampusIssue.id == issue_id)).scalar_one()
    assert issue.version == 2
    assert issue.assignee_membership_id in {c[1].id for c in coordinators}
    assert _status_rows(factory, issue_id) == 1
