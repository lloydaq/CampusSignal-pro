"""Attendance (ACADEMIC-005…007, US-05, US-06).

Assigned faculty record one session per section, date and slot, marking every enrolled student.
They may edit it while the college's edit window is open; after that only a department admin of
the section's department may, with a reason. Every edit is audit-logged with each student's
previous and new status (ACADEMIC-006 requires it; the audit log is the only place these values
are written outside the records themselves, never application logs or notifications).

Deny shape as in academic_setup: no academic role → 403; a section outside the caller's
departments or teaching → 404; a reader who may not write (a college admin, a department admin
recording) → 403.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.pagination import Cursor, newest_first, split_page
from app.models import (
    AcademicTerm,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    ClassSection,
    CollegeMembership,
    Enrollment,
    Subject,
    User,
)
from app.policies.academic import (
    AttendanceEdit,
    attendance_edit,
    attendance_percentage,
    can_read_section,
    can_record_attendance,
    has_own_academics,
    may_read_sections,
)
from app.policies.campus import CampusContext
from app.services.academic_setup import (
    audit_academic,
    current_term,
    load_section,
    section_instructor_ids,
)

EDIT_WINDOW_CLOSED = "Edit window closed — ask your department admin"


def college_today(campus: CampusContext, now: datetime) -> date:
    return now.astimezone(ZoneInfo(campus.college.timezone)).date()


@dataclass(frozen=True)
class SectionAccess:
    section: ClassSection
    subject: Subject
    instructor_ids: list[uuid.UUID]


def _readable(
    db: Session, campus: CampusContext, section_id: uuid.UUID, *, lock: bool = False
) -> SectionAccess:
    if not may_read_sections(campus):
        raise Forbidden()
    section, subject = load_section(db, campus, section_id, lock=lock)
    instructors = section_instructor_ids(db, section)
    if not can_read_section(campus, subject.department_id, instructors):
        raise NotFound()
    return SectionAccess(section, subject, instructors)


def _check_marks(
    marks: list[tuple[uuid.UUID, str]], allowed: set[uuid.UUID], *, complete: bool
) -> dict[uuid.UUID, str]:
    """Marks by enrollment id. Every mark must name an allowed enrollment, at most once; with
    `complete`, every allowed enrollment must be marked."""
    problems: list[dict[str, Any]] = []
    found: dict[uuid.UUID, str] = {}
    for i, (enrollment_id, status) in enumerate(marks):
        if enrollment_id not in allowed:
            problems.append(
                {"field": f"records.{i}.enrollment_id", "message": "Not enrolled in this section."}
            )
        elif enrollment_id in found:
            problems.append(
                {"field": f"records.{i}.enrollment_id", "message": "Marked more than once."}
            )
        else:
            found[enrollment_id] = status
    if complete and not problems and set(found) != allowed:
        problems.append(
            {
                "field": "records",
                "message": f"Mark every enrolled student ({len(allowed - set(found))} missing).",
            }
        )
    if problems:
        raise ValidationFailed(details=problems)
    return found


# --- reading -------------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionView:
    session: AttendanceSession
    recorded_by: tuple[uuid.UUID, str]
    counts: dict[str, int]
    edit: AttendanceEdit | None
    edit_window_closes_at: datetime


@dataclass(frozen=True)
class RecordRow:
    record: AttendanceRecord
    membership_id: uuid.UUID
    display_name: str


def _session_views(
    db: Session,
    campus: CampusContext,
    access: SectionAccess,
    sessions: list[AttendanceSession],
    now: datetime,
) -> list[SessionView]:
    ids = [s.id for s in sessions]
    counts: dict[uuid.UUID, dict[str, int]] = {i: dict.fromkeys(AttendanceStatus, 0) for i in ids}
    names: dict[uuid.UUID, str] = {}
    if ids:
        for session_id, status, count in db.execute(
            select(AttendanceRecord.session_id, AttendanceRecord.status, func.count())
            .where(
                AttendanceRecord.college_id == campus.college_id,
                AttendanceRecord.session_id.in_(ids),
            )
            .group_by(AttendanceRecord.session_id, AttendanceRecord.status)
        ).all():
            counts[session_id][status] = count
        recorders = {s.recorded_by_membership_id for s in sessions}
        names = dict(
            db.execute(
                select(CollegeMembership.id, User.display_name)
                .join(User, User.id == CollegeMembership.user_id)
                .where(
                    CollegeMembership.college_id == campus.college_id,
                    CollegeMembership.id.in_(recorders),
                )
            ).all()
        )
    window = campus.college.attendance_edit_window_hours
    return [
        SessionView(
            session=s,
            recorded_by=(s.recorded_by_membership_id, names.get(s.recorded_by_membership_id, "")),
            counts=counts[s.id],
            edit=attendance_edit(
                campus,
                access.subject.department_id,
                access.instructor_ids,
                created_at=s.created_at,
                window_hours=window,
                now=now,
            ),
            edit_window_closes_at=s.created_at + timedelta(hours=window),
        )
        for s in sessions
    ]


def list_sessions(
    db: Session,
    campus: CampusContext,
    section_id: uuid.UUID,
    *,
    cursor: Cursor | None,
    limit: int,
    now: datetime,
) -> tuple[list[SessionView], str | None]:
    access = _readable(db, campus, section_id)
    statement = select(AttendanceSession).where(
        AttendanceSession.college_id == campus.college_id,
        AttendanceSession.section_id == access.section.id,
    )
    rows = db.execute(
        newest_first(statement, AttendanceSession.created_at, AttendanceSession.id, cursor, limit)
    ).scalars()
    page, next_cursor = split_page(list(rows), limit, lambda s: (s.created_at, s.id))
    return _session_views(db, campus, access, page, now), next_cursor


def _records(db: Session, session: AttendanceSession) -> list[RecordRow]:
    rows = db.execute(
        select(AttendanceRecord, CollegeMembership.id, User.display_name)
        .join(
            Enrollment,
            (Enrollment.college_id == AttendanceRecord.college_id)
            & (Enrollment.id == AttendanceRecord.enrollment_id),
        )
        .join(
            CollegeMembership,
            (CollegeMembership.college_id == Enrollment.college_id)
            & (CollegeMembership.id == Enrollment.membership_id),
        )
        .join(User, User.id == CollegeMembership.user_id)
        .where(
            AttendanceRecord.college_id == session.college_id,
            AttendanceRecord.session_id == session.id,
        )
        .order_by(User.display_name, AttendanceRecord.id)
    ).all()
    return [RecordRow(record, membership_id, name) for record, membership_id, name in rows]


def _load_session(
    db: Session, campus: CampusContext, session_id: uuid.UUID, *, lock: bool = False
) -> AttendanceSession:
    query = select(AttendanceSession).where(
        AttendanceSession.college_id == campus.college_id, AttendanceSession.id == session_id
    )
    session = db.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if session is None:
        raise NotFound()
    return session


def get_session(
    db: Session, campus: CampusContext, session_id: uuid.UUID, now: datetime
) -> tuple[SessionView, list[RecordRow]]:
    if not may_read_sections(campus):
        raise Forbidden()
    session = _load_session(db, campus, session_id)
    access = _readable(db, campus, session.section_id)
    return _session_views(db, campus, access, [session], now)[0], _records(db, session)


# --- recording and editing -----------------------------------------------------------------


def record_session(
    db: Session,
    campus: CampusContext,
    section_id: uuid.UUID,
    *,
    held_on: date,
    slot: int,
    marks: list[tuple[uuid.UUID, str]],
    now: datetime,
) -> tuple[SessionView, list[RecordRow]]:
    """US-06: assigned faculty only (others who can see the section: 403; the rest: 404)."""
    access = _readable(db, campus, section_id, lock=True)
    if not can_record_attendance(campus, access.instructor_ids):
        raise Forbidden("Only the section's assigned faculty record attendance.")
    term = db.execute(
        select(AcademicTerm).where(
            AcademicTerm.college_id == campus.college_id,
            AcademicTerm.id == access.section.term_id,
        )
    ).scalar_one()
    if not term.starts_on <= held_on <= term.ends_on:
        raise ValidationFailed.field(
            "held_on", f"Pick a date in the term ({term.starts_on} to {term.ends_on})."
        )
    if held_on > college_today(campus, now):
        raise ValidationFailed.field("held_on", "The date can't be in the future.")
    enrolled = set(
        db.execute(
            select(Enrollment.id).where(
                Enrollment.college_id == campus.college_id,
                Enrollment.section_id == access.section.id,
            )
        ).scalars()
    )
    if not enrolled:
        raise ValidationFailed.field("records", "No students are enrolled in this section yet.")
    found = _check_marks(marks, enrolled, complete=True)

    session = AttendanceSession(
        college_id=campus.college_id,
        section_id=access.section.id,
        held_on=held_on,
        slot=slot,
        recorded_by_membership_id=campus.membership.id,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(session)
            db.flush()
    except IntegrityError:
        raise Conflict(
            "Attendance for this section, date and period is already recorded.",
            code="session_exists",
        ) from None
    db.add_all(
        AttendanceRecord(
            college_id=campus.college_id,
            session_id=session.id,
            enrollment_id=enrollment_id,
            status=status,
        )
        for enrollment_id, status in found.items()
    )
    audit_academic(
        db,
        campus,
        "attendance_recorded",
        "attendance_session",
        session.id,
        section_id=str(access.section.id),
        students=len(found),
    )
    db.commit()
    return _session_views(db, campus, access, [session], now)[0], _records(db, session)


def _check_version(session: AttendanceSession, version: int) -> None:
    if session.version != version:
        raise Conflict(
            "Someone else changed this attendance. Reload it and try again.",
            code="version_conflict",
        )


def edit_session(
    db: Session,
    campus: CampusContext,
    session_id: uuid.UUID,
    *,
    version: int,
    marks: list[tuple[uuid.UUID, str]],
    reason: str | None,
    now: datetime,
) -> tuple[SessionView, list[RecordRow]]:
    """ACADEMIC-006, US-06. The session row is locked, so two edits from one version can't
    both apply."""
    if not may_read_sections(campus):
        raise Forbidden()
    session = _load_session(db, campus, session_id, lock=True)
    access = _readable(db, campus, session.section_id)
    mode = attendance_edit(
        campus,
        access.subject.department_id,
        access.instructor_ids,
        created_at=session.created_at,
        window_hours=campus.college.attendance_edit_window_hours,
        now=now,
    )
    if mode is None:
        raise Forbidden("Only the section's faculty or its department admin change attendance.")
    if mode == AttendanceEdit.WINDOW_CLOSED:
        raise Forbidden(EDIT_WINDOW_CLOSED, code="edit_window_closed")
    if mode == AttendanceEdit.CORRECTION and not (reason and reason.strip()):
        raise ValidationFailed.field("reason", "Give a reason for the correction.")
    _check_version(session, version)

    records = {r.record.enrollment_id: r.record for r in _records(db, session)}
    found = _check_marks(marks, set(records), complete=False)
    changes = [
        {"enrollment_id": str(enrollment_id), "from": records[enrollment_id].status, "to": status}
        for enrollment_id, status in found.items()
        if records[enrollment_id].status != status
    ]
    if changes:
        for enrollment_id, status in found.items():
            records[enrollment_id].status = status
        session.version += 1
        session.updated_at = now
        audit_academic(
            db,
            campus,
            "attendance_edited",
            "attendance_session",
            session.id,
            reason=reason.strip() if reason else None,
            mode=str(mode),
            changes=changes,
        )
    db.commit()
    return _session_views(db, campus, access, [session], now)[0], _records(db, session)


# --- the student's own attendance (ACADEMIC-007, US-05) ------------------------------------


@dataclass(frozen=True)
class Summary:
    held: int
    attended: int
    excused: int

    @property
    def percentage(self) -> float | None:
        return attendance_percentage(self.held, self.attended, self.excused)


@dataclass(frozen=True)
class MySectionRow:
    section: ClassSection
    subject: Subject
    summary: Summary


def _require_student(campus: CampusContext) -> None:
    if not has_own_academics(campus):
        raise Forbidden()


def my_attendance(
    db: Session, campus: CampusContext
) -> tuple[AcademicTerm | None, list[MySectionRow]]:
    """One row per section the student is enrolled in this term: one aggregate query."""
    _require_student(campus)
    term = current_term(db, campus.college_id)
    if term is None:
        return None, []
    present = func.count(AttendanceRecord.id).filter(
        AttendanceRecord.status == AttendanceStatus.PRESENT
    )
    excused = func.count(AttendanceRecord.id).filter(
        AttendanceRecord.status == AttendanceStatus.EXCUSED
    )
    rows = db.execute(
        select(ClassSection, Subject, func.count(AttendanceRecord.id), present, excused)
        .join(
            Enrollment,
            (Enrollment.college_id == ClassSection.college_id)
            & (Enrollment.section_id == ClassSection.id),
        )
        .join(
            Subject,
            (Subject.college_id == ClassSection.college_id)
            & (Subject.id == ClassSection.subject_id),
        )
        .outerjoin(
            AttendanceRecord,
            (AttendanceRecord.college_id == Enrollment.college_id)
            & (AttendanceRecord.enrollment_id == Enrollment.id),
        )
        .where(
            ClassSection.college_id == campus.college_id,
            ClassSection.term_id == term.id,
            Enrollment.membership_id == campus.membership.id,
        )
        .group_by(ClassSection.id, Subject.id)
        .order_by(Subject.code, ClassSection.name)
    ).all()
    return term, [
        MySectionRow(section, subject, Summary(held, attended, excused_count))
        for section, subject, held, attended, excused_count in rows
    ]


@dataclass(frozen=True)
class MySectionDetail:
    section: ClassSection
    subject: Subject
    term: AcademicTerm
    summary: Summary
    sessions: list[tuple[date, int, str]]


def my_section_attendance(
    db: Session, campus: CampusContext, section_id: uuid.UUID
) -> MySectionDetail:
    """US-05: only a section the caller is enrolled in; anything else is 404."""
    _require_student(campus)
    row = db.execute(
        select(Enrollment, ClassSection, Subject, AcademicTerm)
        .join(
            ClassSection,
            (ClassSection.college_id == Enrollment.college_id)
            & (ClassSection.id == Enrollment.section_id),
        )
        .join(
            Subject,
            (Subject.college_id == ClassSection.college_id)
            & (Subject.id == ClassSection.subject_id),
        )
        .join(
            AcademicTerm,
            (AcademicTerm.college_id == ClassSection.college_id)
            & (AcademicTerm.id == ClassSection.term_id),
        )
        .where(
            Enrollment.college_id == campus.college_id,
            Enrollment.section_id == section_id,
            Enrollment.membership_id == campus.membership.id,
        )
    ).first()
    if row is None:
        raise NotFound()
    enrollment, section, subject, term = row
    sessions = [
        (held_on, slot, status)
        for held_on, slot, status in db.execute(
            select(AttendanceSession.held_on, AttendanceSession.slot, AttendanceRecord.status)
            .join(
                AttendanceSession,
                (AttendanceSession.college_id == AttendanceRecord.college_id)
                & (AttendanceSession.id == AttendanceRecord.session_id),
            )
            .where(
                AttendanceRecord.college_id == campus.college_id,
                AttendanceRecord.enrollment_id == enrollment.id,
            )
            .order_by(AttendanceSession.held_on.desc(), AttendanceSession.slot.desc())
        ).all()
    ]
    summary = Summary(
        held=len(sessions),
        attended=sum(1 for *_, s in sessions if s == AttendanceStatus.PRESENT),
        excused=sum(1 for *_, s in sessions if s == AttendanceStatus.EXCUSED),
    )
    return MySectionDetail(section, subject, term, summary, sessions)
