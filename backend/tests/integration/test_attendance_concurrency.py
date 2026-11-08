"""Two people changing the same attendance at the same moment (ACADEMIC-005, 006).

Two edits made from the same version must not both apply (the session row is locked, then the
version checked), and two recordings of the same section, date and slot create one session.
Independent connections and committed rows, cleaned up afterwards (see test_notice_concurrency).
"""

import threading
import time
import uuid
from collections import Counter
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import Conflict
from app.models import (
    AcademicTerm,
    AttendanceRecord,
    AttendanceSession,
    ClassSection,
    College,
    CollegeMembership,
    CollegeStatus,
    Department,
    Enrollment,
    MembershipKind,
    MembershipStatus,
    SectionInstructor,
    Subject,
)
from app.models.user import User
from app.policies.campus import CampusContext
from app.services import attendance

pytestmark = pytest.mark.integration

TABLES = (
    "attendance_records",
    "attendance_sessions",
    "enrollments",
    "section_instructors",
    "class_sections",
    "subjects",
    "academic_terms",
    "college_memberships",
    "departments",
)


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
            for table in TABLES:
                conn.execute(text(f"DELETE FROM {table} WHERE {race}"))  # noqa: S608 - constants
            conn.execute(text("DELETE FROM colleges WHERE slug LIKE 'race-%'"))
            conn.execute(text("DELETE FROM users WHERE email LIKE 'race-%@northfield.example'"))
        engine.dispose()


@dataclass
class Race:
    college: College
    teachers: list[tuple[User, CollegeMembership]]
    section_id: uuid.UUID
    enrollment_id: uuid.UUID


def _setup(factory: sessionmaker[Session]) -> Race:
    """A college with one section taught by two faculty members, one enrolled student."""
    tag = uuid.uuid4().hex[:10]
    with factory() as db:
        college = College(
            name="Race College",
            slug=f"race-{tag}",
            timezone="UTC",
            status=CollegeStatus.ACTIVE,
        )
        db.add(college)
        db.flush()
        department = Department(college_id=college.id, code="CSE", name="CSE")
        term = AcademicTerm(
            college_id=college.id,
            name="Term",
            starts_on=date(2026, 1, 1),
            ends_on=date(2026, 12, 31),
            is_current=True,
        )
        db.add_all([department, term])
        db.flush()
        subject = Subject(
            college_id=college.id, department_id=department.id, code="CS1", name="CS1"
        )
        db.add(subject)
        db.flush()
        section = ClassSection(
            college_id=college.id, term_id=term.id, subject_id=subject.id, name="A"
        )
        db.add(section)
        db.flush()

        def member(n: str, kind: MembershipKind) -> tuple[User, CollegeMembership]:
            user = User(
                email=f"race-{n}-{tag}@northfield.example", password_hash="x", display_name=n
            )
            db.add(user)
            db.flush()
            membership = CollegeMembership(
                user_id=user.id,
                college_id=college.id,
                kind=kind,
                status=MembershipStatus.ACTIVE,
                department_id=department.id,
            )
            db.add(membership)
            db.flush()
            return user, membership

        teachers = [member(f"t{n}", MembershipKind.FACULTY) for n in range(2)]
        for _, membership in teachers:
            db.add(
                SectionInstructor(
                    college_id=college.id, section_id=section.id, membership_id=membership.id
                )
            )
        _, student = member("s", MembershipKind.STUDENT)
        enrollment = Enrollment(
            college_id=college.id, section_id=section.id, membership_id=student.id
        )
        db.add(enrollment)
        db.commit()
        return Race(college, teachers, section.id, enrollment.id)


@pytest.fixture
def slow_version_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pause just after the version check so both edits reach the write together: a missing
    row lock would then always show."""
    original = attendance._check_version

    def checked_then_paused(*args: Any) -> None:
        original(*args)
        time.sleep(0.3)

    monkeypatch.setattr(attendance, "_check_version", checked_then_paused)


def _race(factory: sessionmaker[Session], race: Race, act: Any) -> Counter[str]:
    barrier = threading.Barrier(2)

    def run(index: int) -> str:
        user, membership = race.teachers[index]
        barrier.wait(timeout=30)
        with factory() as db:
            campus = CampusContext(
                user=user, membership=membership, college=race.college, grants=()
            )
            try:
                act(db, campus, index)
            except Conflict as exc:
                return exc.error_code
            return "ok"

    with ThreadPoolExecutor(max_workers=2) as pool:
        return Counter(pool.map(run, range(2)))


@pytest.mark.parametrize("round_", range(2))
def test_two_edits_from_the_same_version_cannot_both_apply(
    factory: sessionmaker[Session], slow_version_check: None, round_: int
) -> None:
    race = _setup(factory)
    now = datetime.now(UTC)
    with factory() as db:
        user, membership = race.teachers[0]
        campus = CampusContext(user=user, membership=membership, college=race.college, grants=())
        view, _ = attendance.record_session(
            db,
            campus,
            race.section_id,
            held_on=date(2026, 3, 2),
            slot=1,
            marks=[(race.enrollment_id, "PRESENT")],
            now=now,
        )
        session_id = view.session.id

    def edit(db: Session, campus: CampusContext, index: int) -> None:
        status = ("ABSENT", "EXCUSED")[index]
        attendance.edit_session(
            db,
            campus,
            session_id,
            version=1,
            marks=[(race.enrollment_id, status)],
            reason=None,
            now=datetime.now(UTC),
        )

    assert _race(factory, race, edit) == {"ok": 1, "version_conflict": 1}
    with factory() as db:
        session = db.execute(
            select(AttendanceSession).where(AttendanceSession.id == session_id)
        ).scalar_one()
        status = db.execute(
            select(AttendanceRecord.status).where(AttendanceRecord.session_id == session_id)
        ).scalar_one()
        edits = db.execute(
            text(
                "SELECT count(*) FROM audit_log "
                "WHERE action = 'academic.attendance_edited' AND target_id = :t"
            ),
            {"t": str(session_id)},
        ).scalar_one()
    assert (session.version, edits) == (2, 1)
    assert status in {"ABSENT", "EXCUSED"}


@pytest.mark.parametrize("round_", range(2))
def test_two_recordings_of_one_slot_create_one_session(
    factory: sessionmaker[Session], round_: int
) -> None:
    race = _setup(factory)

    def record(db: Session, campus: CampusContext, index: int) -> None:
        attendance.record_session(
            db,
            campus,
            race.section_id,
            held_on=date(2026, 3, 2),
            slot=1,
            marks=[(race.enrollment_id, ("PRESENT", "ABSENT")[index])],
            now=datetime.now(UTC),
        )

    assert _race(factory, race, record) == {"ok": 1, "session_exists": 1}
    with factory() as db:
        sessions = db.execute(
            select(func.count())
            .select_from(AttendanceSession)
            .where(AttendanceSession.section_id == race.section_id)
        ).scalar_one()
        records = db.execute(
            select(func.count())
            .select_from(AttendanceRecord)
            .where(AttendanceRecord.college_id == race.college.id)
        ).scalar_one()
    assert (sessions, records) == (1, 1)
