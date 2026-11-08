"""Academic setup (ACADEMIC-001…004): terms, subjects, sections, instructors, enrollment and the
timetable, plus the student's week and the faculty member's sections.

Every function checks the caller's role first (403 for none), then loads the object inside the
acting college (404 if absent or elsewhere), then applies app/policies/academic.py (404 for an
object outside the caller's departments or sections). Audit entries carry ids and counts only:
never roll numbers.
"""

import csv
import io
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import Select, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.pagination import Cursor, newest_first, split_page
from app.models import (
    AcademicTerm,
    AttendanceSession,
    ClassSection,
    CollegeMembership,
    Department,
    Enrollment,
    MembershipStatus,
    RosterEntry,
    SectionInstructor,
    Subject,
    TimetableEntry,
    User,
)
from app.policies.academic import (
    can_manage_catalog,
    can_manage_terms,
    can_read_section,
    enrollment_problem,
    has_own_academics,
    instructor_problem,
    is_teacher,
    managed_departments,
    manages_any_catalog,
    may_read_sections,
)
from app.policies.campus import CampusContext
from app.services.audit import record_audit
from app.services.roster import ROLL_NUMBER, Problem, RosterInvalid

MAX_ENROLLMENT_ROWS = 1000
MAX_REPORTED_PROBLEMS = 200


def _violated(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def audit_academic(
    db: Session,
    campus: CampusContext,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    *,
    reason: str | None = None,
    **data: object,
) -> None:
    record_audit(
        db,
        action=f"academic.{action}",
        actor_user_id=campus.user.id,
        college_id=campus.college_id,
        target_type=target_type,
        target_id=str(target_id),
        reason=reason,
        metadata=dict(data),
    )


def _require_catalog_role(campus: CampusContext) -> None:
    if not manages_any_catalog(campus):
        raise Forbidden()


def _authorize_catalog(campus: CampusContext, department_id: uuid.UUID) -> None:
    if not can_manage_catalog(campus, department_id):
        raise NotFound()


# --- terms (ACADEMIC-001) ------------------------------------------------------------------


def _term_conflict(exc: IntegrityError) -> Conflict:
    if _violated(exc) == "uq_academic_terms_one_current":
        return Conflict(
            "Another term is already current. Make it not current first.",
            code="current_term_exists",
        )
    return Conflict("A term with this name already exists.", code="term_name_taken")


def list_terms(db: Session, campus: CampusContext) -> list[AcademicTerm]:
    _require_catalog_role(campus)  # department admins pick a term for their sections
    return list(
        db.execute(
            select(AcademicTerm)
            .where(AcademicTerm.college_id == campus.college_id)
            .order_by(AcademicTerm.starts_on.desc(), AcademicTerm.id)
        ).scalars()
    )


def create_term(
    db: Session,
    campus: CampusContext,
    *,
    name: str,
    starts_on: date,
    ends_on: date,
    is_current: bool,
    now: datetime,
) -> AcademicTerm:
    if not can_manage_terms(campus):
        raise Forbidden()
    term = AcademicTerm(
        college_id=campus.college_id,
        name=name,
        starts_on=starts_on,
        ends_on=ends_on,
        is_current=is_current,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(term)
            db.flush()
    except IntegrityError as exc:
        raise _term_conflict(exc) from None
    audit_academic(db, campus, "term_created", "academic_term", term.id, is_current=is_current)
    db.commit()
    return term


def update_term(
    db: Session,
    campus: CampusContext,
    term_id: uuid.UUID,
    *,
    name: str | None,
    starts_on: date | None,
    ends_on: date | None,
    is_current: bool | None,
    now: datetime,
) -> AcademicTerm:
    if not can_manage_terms(campus):
        raise Forbidden()
    term = db.execute(
        select(AcademicTerm)
        .where(AcademicTerm.college_id == campus.college_id, AcademicTerm.id == term_id)
        .with_for_update()
    ).scalar_one_or_none()
    if term is None:
        raise NotFound()
    new_start = starts_on if starts_on is not None else term.starts_on
    new_end = ends_on if ends_on is not None else term.ends_on
    if new_start >= new_end:
        raise ValidationFailed.field("ends_on", "The term must end after it starts.")
    if (new_start, new_end) != (term.starts_on, term.ends_on) and _has_sessions_outside(
        db, term, new_start, new_end
    ):
        raise Conflict(
            "Attendance is already recorded outside these dates. Keep the term around it.",
            code="term_has_sessions_outside",
        )
    changes = {
        field: value
        for field, value in (
            ("name", name),
            ("starts_on", starts_on),
            ("ends_on", ends_on),
            ("is_current", is_current),
        )
        if value is not None and value != getattr(term, field)
    }
    if not changes:
        return term
    try:
        with db.begin_nested():
            for field, value in changes.items():
                setattr(term, field, value)
            term.updated_at = now
            db.flush()
    except IntegrityError as exc:
        raise _term_conflict(exc) from None
    audit_academic(db, campus, "term_updated", "academic_term", term.id, changes=sorted(changes))
    db.commit()
    return term


def _has_sessions_outside(db: Session, term: AcademicTerm, starts_on: date, ends_on: date) -> bool:
    """Would these dates leave recorded attendance outside its term (ACADEMIC-005)?"""
    return bool(
        db.execute(
            select(
                exists().where(
                    AttendanceSession.college_id == term.college_id,
                    AttendanceSession.section_id == ClassSection.id,
                    ClassSection.college_id == term.college_id,
                    ClassSection.term_id == term.id,
                    (AttendanceSession.held_on < starts_on) | (AttendanceSession.held_on > ends_on),
                )
            )
        ).scalar()
    )


def current_term(db: Session, college_id: uuid.UUID) -> AcademicTerm | None:
    return db.execute(
        select(AcademicTerm).where(AcademicTerm.college_id == college_id, AcademicTerm.is_current)
    ).scalar_one_or_none()


# --- subjects (ACADEMIC-002) ---------------------------------------------------------------


def _load_subject(
    db: Session, campus: CampusContext, subject_id: uuid.UUID
) -> tuple[Subject, Department]:
    row = db.execute(
        select(Subject, Department)
        .join(
            Department,
            (Department.college_id == Subject.college_id)
            & (Department.id == Subject.department_id),
        )
        .where(Subject.college_id == campus.college_id, Subject.id == subject_id)
    ).first()
    if row is None:
        raise NotFound()
    return row[0], row[1]


def list_subjects(
    db: Session,
    campus: CampusContext,
    *,
    department_id: uuid.UUID | None,
    query: str | None,
    cursor: Cursor | None,
    limit: int,
) -> tuple[list[tuple[Subject, Department]], str | None]:
    _require_catalog_role(campus)
    statement = (
        select(Subject, Department)
        .join(
            Department,
            (Department.college_id == Subject.college_id)
            & (Department.id == Subject.department_id),
        )
        .where(Subject.college_id == campus.college_id)
    )
    scope = managed_departments(campus)
    if scope is not None:
        statement = statement.where(Subject.department_id.in_(scope))
    if department_id is not None:
        statement = statement.where(Subject.department_id == department_id)
    if query:
        statement = statement.where(
            Subject.code.icontains(query, autoescape=True)
            | Subject.name.icontains(query, autoescape=True)
        )
    rows = db.execute(newest_first(statement, Subject.created_at, Subject.id, cursor, limit)).all()
    page, next_cursor = split_page(list(rows), limit, lambda r: (r[0].created_at, r[0].id))
    return [(s, d) for s, d in page], next_cursor


def create_subject(
    db: Session,
    campus: CampusContext,
    *,
    department_id: uuid.UUID,
    code: str,
    name: str,
    now: datetime,
) -> tuple[Subject, Department]:
    _require_catalog_role(campus)
    department = db.execute(
        select(Department).where(
            Department.college_id == campus.college_id, Department.id == department_id
        )
    ).scalar_one_or_none()
    if department is None or not can_manage_catalog(campus, department.id):
        raise NotFound()
    if department.archived_at is not None:
        raise ValidationFailed.field("department_id", "This department is archived.")
    subject = Subject(
        college_id=campus.college_id,
        department_id=department.id,
        code=code,
        name=name,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(subject)
            db.flush()
    except IntegrityError:
        raise Conflict("A subject with this code already exists.", code="code_taken") from None
    audit_academic(db, campus, "subject_created", "subject", subject.id, code=code)
    db.commit()
    return subject, department


def update_subject(
    db: Session, campus: CampusContext, subject_id: uuid.UUID, *, name: str, now: datetime
) -> tuple[Subject, Department]:
    _require_catalog_role(campus)
    subject, department = _load_subject(db, campus, subject_id)
    _authorize_catalog(campus, department.id)
    if name != subject.name:
        subject.name = name
        subject.updated_at = now
        audit_academic(db, campus, "subject_updated", "subject", subject.id, changes=["name"])
        db.commit()
    return subject, department


def delete_subject(db: Session, campus: CampusContext, subject_id: uuid.UUID) -> None:
    _require_catalog_role(campus)
    subject, department = _load_subject(db, campus, subject_id)
    _authorize_catalog(campus, department.id)
    try:
        with db.begin_nested():
            db.delete(subject)
            db.flush()
    except IntegrityError:
        raise Conflict(
            "This subject has sections. Delete them first.", code="subject_in_use"
        ) from None
    audit_academic(db, campus, "subject_deleted", "subject", subject_id, code=subject.code)
    db.commit()


# --- sections (ACADEMIC-002, 010) ----------------------------------------------------------


@dataclass(frozen=True)
class SectionView:
    section: ClassSection
    term: AcademicTerm
    subject: Subject
    department: Department
    instructors: list[tuple[uuid.UUID, str]]  # (membership id, display name)
    enrollment_count: int


def _section_query() -> Select[ClassSection, AcademicTerm, Subject, Department]:
    return (
        select(ClassSection, AcademicTerm, Subject, Department)
        .join(
            AcademicTerm,
            (AcademicTerm.college_id == ClassSection.college_id)
            & (AcademicTerm.id == ClassSection.term_id),
        )
        .join(
            Subject,
            (Subject.college_id == ClassSection.college_id)
            & (Subject.id == ClassSection.subject_id),
        )
        .join(
            Department,
            (Department.college_id == Subject.college_id)
            & (Department.id == Subject.department_id),
        )
    )


def _views(
    db: Session,
    college_id: uuid.UUID,
    rows: list[tuple[ClassSection, AcademicTerm, Subject, Department]],
) -> list[SectionView]:
    """Section views with their instructors and enrollment counts: two queries for the page."""
    ids = [row[0].id for row in rows]
    instructors: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)
    counts: dict[uuid.UUID, int] = {}
    if ids:
        for section_id, membership_id, display_name in db.execute(
            select(SectionInstructor.section_id, CollegeMembership.id, User.display_name)
            .join(
                CollegeMembership,
                (CollegeMembership.college_id == SectionInstructor.college_id)
                & (CollegeMembership.id == SectionInstructor.membership_id),
            )
            .join(User, User.id == CollegeMembership.user_id)
            .where(
                SectionInstructor.college_id == college_id, SectionInstructor.section_id.in_(ids)
            )
            .order_by(User.display_name, CollegeMembership.id)
        ):
            instructors[section_id].append((membership_id, display_name))
        counts = {
            section_id: count
            for section_id, count in db.execute(
                select(Enrollment.section_id, func.count())
                .where(Enrollment.college_id == college_id, Enrollment.section_id.in_(ids))
                .group_by(Enrollment.section_id)
            ).all()
        }
    return [
        SectionView(
            section, term, subject, department, instructors[section.id], counts.get(section.id, 0)
        )
        for section, term, subject, department in rows
    ]


def load_section(
    db: Session, campus: CampusContext, section_id: uuid.UUID, *, lock: bool = False
) -> tuple[ClassSection, Subject]:
    query = (
        select(ClassSection, Subject)
        .join(
            Subject,
            (Subject.college_id == ClassSection.college_id)
            & (Subject.id == ClassSection.subject_id),
        )
        .where(ClassSection.college_id == campus.college_id, ClassSection.id == section_id)
    )
    row = db.execute(query.with_for_update(of=ClassSection) if lock else query).first()
    if row is None:
        raise NotFound()
    return row[0], row[1]


def section_instructor_ids(db: Session, section: ClassSection) -> list[uuid.UUID]:
    return list(
        db.execute(
            select(SectionInstructor.membership_id).where(
                SectionInstructor.college_id == section.college_id,
                SectionInstructor.section_id == section.id,
            )
        ).scalars()
    )


def _readable_section(db: Session, campus: CampusContext, section_id: uuid.UUID) -> ClassSection:
    """The section if the caller may read it (managers of its department, its faculty)."""
    if not may_read_sections(campus):
        raise Forbidden()
    section, subject = load_section(db, campus, section_id)
    if not can_read_section(campus, subject.department_id, section_instructor_ids(db, section)):
        raise NotFound()
    return section


def _managed_section(
    db: Session, campus: CampusContext, section_id: uuid.UUID, *, lock: bool = False
) -> tuple[ClassSection, Subject]:
    _require_catalog_role(campus)
    section, subject = load_section(db, campus, section_id, lock=lock)
    _authorize_catalog(campus, subject.department_id)
    return section, subject


def _view(db: Session, campus: CampusContext, section_id: uuid.UUID) -> SectionView:
    row = db.execute(
        _section_query().where(
            ClassSection.college_id == campus.college_id, ClassSection.id == section_id
        )
    ).one()
    section, term, subject, department = row
    return _views(db, campus.college_id, [(section, term, subject, department)])[0]


def get_section(db: Session, campus: CampusContext, section_id: uuid.UUID) -> SectionView:
    section = _readable_section(db, campus, section_id)
    return _view(db, campus, section.id)


def list_sections(
    db: Session,
    campus: CampusContext,
    *,
    term_id: uuid.UUID | None,
    subject_id: uuid.UUID | None,
    department_id: uuid.UUID | None,
    cursor: Cursor | None,
    limit: int,
) -> tuple[list[SectionView], str | None]:
    _require_catalog_role(campus)  # faculty use /teaching/sections
    statement = _section_query().where(ClassSection.college_id == campus.college_id)
    scope = managed_departments(campus)
    if scope is not None:
        statement = statement.where(Subject.department_id.in_(scope))
    if term_id is not None:
        statement = statement.where(ClassSection.term_id == term_id)
    if subject_id is not None:
        statement = statement.where(ClassSection.subject_id == subject_id)
    if department_id is not None:
        statement = statement.where(Subject.department_id == department_id)
    rows = db.execute(
        newest_first(statement, ClassSection.created_at, ClassSection.id, cursor, limit)
    ).all()
    page, next_cursor = split_page(
        [(s, t, subj, d) for s, t, subj, d in rows], limit, lambda r: (r[0].created_at, r[0].id)
    )
    return _views(db, campus.college_id, page), next_cursor


def create_section(
    db: Session,
    campus: CampusContext,
    *,
    term_id: uuid.UUID,
    subject_id: uuid.UUID,
    name: str,
    now: datetime,
) -> SectionView:
    _require_catalog_role(campus)
    subject, department = _load_subject(db, campus, subject_id)
    _authorize_catalog(campus, department.id)  # US-13: another department's subject → 404
    term = db.execute(
        select(AcademicTerm).where(
            AcademicTerm.college_id == campus.college_id, AcademicTerm.id == term_id
        )
    ).scalar_one_or_none()
    if term is None:
        raise NotFound()
    section = ClassSection(
        college_id=campus.college_id,
        term_id=term.id,
        subject_id=subject.id,
        name=name,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(section)
            db.flush()
    except IntegrityError:
        raise Conflict(
            "This subject already has a section with this name in this term.", code="section_exists"
        ) from None
    audit_academic(db, campus, "section_created", "class_section", section.id)
    db.commit()
    return _view(db, campus, section.id)


def update_section(
    db: Session, campus: CampusContext, section_id: uuid.UUID, *, name: str, now: datetime
) -> SectionView:
    section, _ = _managed_section(db, campus, section_id)
    if name != section.name:
        try:
            with db.begin_nested():
                section.name = name
                section.updated_at = now
                db.flush()
        except IntegrityError:
            raise Conflict(
                "This subject already has a section with this name in this term.",
                code="section_exists",
            ) from None
        audit_academic(db, campus, "section_updated", "class_section", section.id, changes=["name"])
        db.commit()
    return _view(db, campus, section.id)


def delete_section(db: Session, campus: CampusContext, section_id: uuid.UUID) -> None:
    """Instructors and timetable entries go with the section; enrollments block it."""
    section, _ = _managed_section(db, campus, section_id, lock=True)
    try:
        with db.begin_nested():
            db.delete(section)
            db.flush()
    except IntegrityError:
        raise Conflict(
            "This section has enrolled students. Remove them first.",
            code="section_has_enrollments",
        ) from None
    audit_academic(db, campus, "section_deleted", "class_section", section_id)
    db.commit()


# --- instructors (ACADEMIC-002) ------------------------------------------------------------


def _members(
    db: Session, college_id: uuid.UUID, ids: list[uuid.UUID]
) -> dict[uuid.UUID, CollegeMembership]:
    """Memberships of this college among `ids`. Ids of other colleges simply aren't found."""
    if not ids:
        return {}
    return {
        m.id: m
        for m in db.execute(
            select(CollegeMembership).where(
                CollegeMembership.college_id == college_id, CollegeMembership.id.in_(ids)
            )
        ).scalars()
    }


def set_instructors(
    db: Session,
    campus: CampusContext,
    section_id: uuid.UUID,
    membership_ids: list[uuid.UUID],
    now: datetime,
) -> SectionView:
    section, _ = _managed_section(db, campus, section_id, lock=True)
    wanted = list(dict.fromkeys(membership_ids))
    found = _members(db, campus.college_id, wanted)
    problems = [
        {"field": f"membership_ids.{i}", "message": "Not an active faculty member of this college."}
        for i, member_id in enumerate(wanted)
        if member_id not in found or instructor_problem(found[member_id]) is not None
    ]
    if problems:
        raise ValidationFailed(details=problems)
    current = {
        row.membership_id: row
        for row in db.execute(
            select(SectionInstructor).where(
                SectionInstructor.college_id == campus.college_id,
                SectionInstructor.section_id == section.id,
            )
        ).scalars()
    }
    removed = [row for member_id, row in current.items() if member_id not in found]
    added = [member_id for member_id in wanted if member_id not in current]
    for row in removed:
        db.delete(row)
    db.add_all(
        SectionInstructor(
            college_id=campus.college_id, section_id=section.id, membership_id=m, created_at=now
        )
        for m in added
    )
    if removed or added:
        audit_academic(
            db,
            campus,
            "instructors_set",
            "class_section",
            section.id,
            added=len(added),
            removed=len(removed),
        )
    db.commit()
    return _view(db, campus, section.id)


# --- enrollments (ACADEMIC-002) ------------------------------------------------------------


class EnrollmentInvalid(RosterInvalid):
    code = "enrollment_invalid"
    default_message = "The file has problems. Nobody was enrolled."


def _file_problem(message: str) -> EnrollmentInvalid:
    return EnrollmentInvalid(details=[Problem(1, None, message).as_detail()])


def _enroll(
    db: Session,
    campus: CampusContext,
    section: ClassSection,
    member_ids: list[uuid.UUID],
    now: datetime,
) -> tuple[int, int]:
    inserted = db.execute(
        insert(Enrollment)
        .values(
            [
                {
                    "college_id": campus.college_id,
                    "section_id": section.id,
                    "membership_id": m,
                    "created_at": now,
                }
                for m in member_ids
            ]
        )
        .on_conflict_do_nothing(index_elements=["section_id", "membership_id"])
        .returning(Enrollment.id)
    ).all()
    enrolled = len(inserted)
    already = len(member_ids) - enrolled
    if enrolled:
        audit_academic(
            db,
            campus,
            "enrollments_added",
            "class_section",
            section.id,
            enrolled=enrolled,
            already_enrolled=already,
        )
    db.commit()
    return enrolled, already


def import_enrollments(
    db: Session, campus: CampusContext, section_id: uuid.UUID, *, text: str, now: datetime
) -> tuple[int, int]:
    """US-13: a CSV with one `roll_number` column. Unknown roll numbers, or ones without an
    ACTIVE student behind them, reject the whole file, listing every bad row."""
    section, _ = _managed_section(db, campus, section_id, lock=True)
    if not text.strip():
        raise _file_problem("The file is empty.")
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    if header != ["roll_number"]:
        raise _file_problem("The header must be exactly one column: roll_number.")
    reader.fieldnames = header

    rows: list[tuple[int, str]] = []
    problems: list[Problem] = []
    seen: set[str] = set()
    for raw in reader:
        roll = (raw.get("roll_number") or "").strip().upper()
        if not roll and not any((v or "").strip() for k, v in raw.items() if k is not None):
            continue  # blank line
        if len(rows) + len(problems) >= MAX_ENROLLMENT_ROWS:
            raise _file_problem(f"Enroll at most {MAX_ENROLLMENT_ROWS} students at a time.")
        if not ROLL_NUMBER.match(roll):
            problems.append(Problem(reader.line_num, "roll_number", "Not a valid roll number."))
        elif roll in seen:
            problems.append(Problem(reader.line_num, "roll_number", "Appears twice in this file."))
        else:
            rows.append((reader.line_num, roll))
        seen.add(roll)

    # A roster entry backs at most one ACTIVE membership (MEMBER-005).
    holders = {
        roll: membership
        for roll, membership in db.execute(
            select(RosterEntry.roll_number, CollegeMembership)
            .join(
                CollegeMembership,
                (CollegeMembership.college_id == RosterEntry.college_id)
                & (CollegeMembership.roster_entry_id == RosterEntry.id)
                & (CollegeMembership.status == MembershipStatus.ACTIVE),
            )
            .where(
                RosterEntry.college_id == campus.college_id,
                RosterEntry.roll_number.in_([roll for _, roll in rows]),
            )
        ).all()
    }
    member_ids: list[uuid.UUID] = []
    for line, roll in rows:
        membership = holders.get(roll)
        if membership is None or enrollment_problem(membership) is not None:
            problems.append(Problem(line, "roll_number", "No active student has this roll number."))
        else:
            member_ids.append(membership.id)
    if problems:
        problems.sort(key=lambda p: p.row)
        raise EnrollmentInvalid(details=[p.as_detail() for p in problems[:MAX_REPORTED_PROBLEMS]])
    if not member_ids:
        raise _file_problem("The file has no rows to import.")
    return _enroll(db, campus, section, member_ids, now)


def add_enrollments(
    db: Session,
    campus: CampusContext,
    section_id: uuid.UUID,
    membership_ids: list[uuid.UUID],
    now: datetime,
) -> tuple[int, int]:
    section, _ = _managed_section(db, campus, section_id, lock=True)
    wanted = list(dict.fromkeys(membership_ids))
    found = _members(db, campus.college_id, wanted)
    problems = [
        {"field": f"membership_ids.{i}", "message": "Not an active student of this college."}
        for i, member_id in enumerate(wanted)
        if member_id not in found or enrollment_problem(found[member_id]) is not None
    ]
    if problems:
        raise ValidationFailed(details=problems)
    return _enroll(db, campus, section, wanted, now)


@dataclass(frozen=True)
class EnrollmentRow:
    enrollment: Enrollment
    display_name: str
    roll_number: str | None
    department: Department | None


def list_enrollments(
    db: Session,
    campus: CampusContext,
    section_id: uuid.UUID,
    *,
    cursor: Cursor | None,
    limit: int,
) -> tuple[list[EnrollmentRow], str | None]:
    section = _readable_section(db, campus, section_id)
    subject_department = db.execute(
        select(Subject.department_id).where(
            Subject.college_id == campus.college_id, Subject.id == section.subject_id
        )
    ).scalar_one()
    # §17.6: roll numbers only for those who manage the section's department.
    show_roll = can_manage_catalog(campus, subject_department)
    statement = (
        select(Enrollment, User.display_name, RosterEntry.roll_number, Department)
        .join(
            CollegeMembership,
            (CollegeMembership.college_id == Enrollment.college_id)
            & (CollegeMembership.id == Enrollment.membership_id),
        )
        .join(User, User.id == CollegeMembership.user_id)
        .outerjoin(
            RosterEntry,
            (RosterEntry.college_id == CollegeMembership.college_id)
            & (RosterEntry.id == CollegeMembership.roster_entry_id),
        )
        .outerjoin(
            Department,
            (Department.college_id == CollegeMembership.college_id)
            & (Department.id == CollegeMembership.department_id),
        )
        .where(Enrollment.college_id == campus.college_id, Enrollment.section_id == section.id)
    )
    rows = db.execute(
        newest_first(statement, Enrollment.created_at, Enrollment.id, cursor, limit)
    ).all()
    page, next_cursor = split_page(list(rows), limit, lambda r: (r[0].created_at, r[0].id))
    return [
        EnrollmentRow(enrollment, name, roll if show_roll else None, department)
        for enrollment, name, roll, department in page
    ], next_cursor


def remove_enrollment(db: Session, campus: CampusContext, enrollment_id: uuid.UUID) -> None:
    """ACADEMIC-002: an enrollment with attendance or results can't be removed (409; the
    records' foreign keys enforce it once 7b/7c add them)."""
    _require_catalog_role(campus)
    enrollment = db.execute(
        select(Enrollment).where(
            Enrollment.college_id == campus.college_id, Enrollment.id == enrollment_id
        )
    ).scalar_one_or_none()
    if enrollment is None:
        raise NotFound()
    section, _ = _managed_section(db, campus, enrollment.section_id, lock=True)
    try:
        with db.begin_nested():
            db.delete(enrollment)
            db.flush()
    except IntegrityError:
        raise Conflict(
            "This student already has attendance or results in this section.",
            code="enrollment_has_records",
        ) from None
    audit_academic(db, campus, "enrollment_removed", "class_section", section.id)
    db.commit()


# --- timetable (ACADEMIC-003, 004) ---------------------------------------------------------


def _overlap() -> Conflict:
    return Conflict(
        "This section already has a class at that time on that day.", code="timetable_overlap"
    )


def list_timetable(
    db: Session, campus: CampusContext, section_id: uuid.UUID
) -> list[TimetableEntry]:
    section = _readable_section(db, campus, section_id)
    return list(
        db.execute(
            select(TimetableEntry)
            .where(
                TimetableEntry.college_id == campus.college_id,
                TimetableEntry.section_id == section.id,
            )
            .order_by(TimetableEntry.weekday, TimetableEntry.starts_at, TimetableEntry.id)
        ).scalars()
    )


def add_timetable_entry(
    db: Session,
    campus: CampusContext,
    section_id: uuid.UUID,
    *,
    weekday: int,
    starts_at: time,
    ends_at: time,
    room: str,
    now: datetime,
) -> TimetableEntry:
    section, _ = _managed_section(db, campus, section_id)
    entry = TimetableEntry(
        college_id=campus.college_id,
        section_id=section.id,
        weekday=weekday,
        starts_at=starts_at,
        ends_at=ends_at,
        room=room,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(entry)
            db.flush()
    except IntegrityError:
        raise _overlap() from None
    audit_academic(db, campus, "timetable_entry_created", "timetable_entry", entry.id)
    db.commit()
    return entry


def _managed_entry(db: Session, campus: CampusContext, entry_id: uuid.UUID) -> TimetableEntry:
    _require_catalog_role(campus)
    entry = db.execute(
        select(TimetableEntry).where(
            TimetableEntry.college_id == campus.college_id, TimetableEntry.id == entry_id
        )
    ).scalar_one_or_none()
    if entry is None:
        raise NotFound()
    _managed_section(db, campus, entry.section_id)
    return entry


def update_timetable_entry(
    db: Session,
    campus: CampusContext,
    entry_id: uuid.UUID,
    *,
    weekday: int | None,
    starts_at: time | None,
    ends_at: time | None,
    room: str | None,
    now: datetime,
) -> TimetableEntry:
    entry = _managed_entry(db, campus, entry_id)
    new_start = starts_at if starts_at is not None else entry.starts_at
    new_end = ends_at if ends_at is not None else entry.ends_at
    if new_start >= new_end:
        raise ValidationFailed.field("ends_at", "The class must end after it starts.")
    changes = {
        field: value
        for field, value in (
            ("weekday", weekday),
            ("starts_at", starts_at),
            ("ends_at", ends_at),
            ("room", room),
        )
        if value is not None and value != getattr(entry, field)
    }
    if not changes:
        return entry
    try:
        with db.begin_nested():
            for field, value in changes.items():
                setattr(entry, field, value)
            entry.updated_at = now
            db.flush()
    except IntegrityError:
        raise _overlap() from None
    audit_academic(
        db, campus, "timetable_entry_updated", "timetable_entry", entry.id, changes=sorted(changes)
    )
    db.commit()
    return entry


def delete_timetable_entry(db: Session, campus: CampusContext, entry_id: uuid.UUID) -> None:
    entry = _managed_entry(db, campus, entry_id)
    db.delete(entry)
    audit_academic(db, campus, "timetable_entry_deleted", "timetable_entry", entry_id)
    db.commit()


@dataclass(frozen=True)
class MyClassRow:
    entry: TimetableEntry
    section: ClassSection
    subject: Subject


def my_timetable(
    db: Session, campus: CampusContext
) -> tuple[AcademicTerm | None, list[MyClassRow]]:
    """ACADEMIC-004, US-13: only the caller's own enrolled sections, current term only."""
    if not has_own_academics(campus):
        raise Forbidden()
    term = current_term(db, campus.college_id)
    if term is None:
        return None, []
    rows = db.execute(
        select(TimetableEntry, ClassSection, Subject)
        .join(
            ClassSection,
            (ClassSection.college_id == TimetableEntry.college_id)
            & (ClassSection.id == TimetableEntry.section_id),
        )
        .join(
            Subject,
            (Subject.college_id == ClassSection.college_id)
            & (Subject.id == ClassSection.subject_id),
        )
        .join(
            Enrollment,
            (Enrollment.college_id == ClassSection.college_id)
            & (Enrollment.section_id == ClassSection.id),
        )
        .where(
            TimetableEntry.college_id == campus.college_id,
            ClassSection.term_id == term.id,
            Enrollment.membership_id == campus.membership.id,
        )
        .order_by(TimetableEntry.weekday, TimetableEntry.starts_at, TimetableEntry.id)
    ).all()
    return term, [MyClassRow(e, s, subj) for e, s, subj in rows]


def teaching_sections(
    db: Session, campus: CampusContext
) -> tuple[AcademicTerm | None, list[SectionView]]:
    """The caller's assigned sections in the current term (ACADEMIC-010)."""
    if not is_teacher(campus):
        raise Forbidden()
    term = current_term(db, campus.college_id)
    if term is None:
        return None, []
    rows = db.execute(
        _section_query()
        .join(
            SectionInstructor,
            (SectionInstructor.college_id == ClassSection.college_id)
            & (SectionInstructor.section_id == ClassSection.id),
        )
        .where(
            ClassSection.college_id == campus.college_id,
            ClassSection.term_id == term.id,
            SectionInstructor.membership_id == campus.membership.id,
        )
        .order_by(Subject.code, ClassSection.name)
    ).all()
    return term, _views(db, campus.college_id, [(s, t, subj, d) for s, t, subj, d in rows])
