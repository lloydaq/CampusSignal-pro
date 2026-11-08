"""Assessments and results (ACADEMIC-008, 009, US-07).

Assigned faculty create assessments and enter scores (0 to the maximum, or ABSENT). Nothing
about an assessment reaches students until it's published, by its faculty or a department
admin of the section's department; publishing needs every enrolled student scored and tells
each of them once. After that, only its faculty change scores, with a reason: the changed
results are marked revised and their students told.

Scores never go into notifications, logs or error messages (Rules R-2.11). The audit log
records who changed which students' results and why, not the values (ADMIN-006).

Deny shape as in attendance: no academic role → 403; a section outside the caller's
departments or teaching → 404; a reader who may not write → 403.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.pagination import Cursor, newest_first, split_page
from app.models import (
    AcademicTerm,
    Assessment,
    AssessmentResult,
    ClassSection,
    CollegeMembership,
    Enrollment,
    MembershipStatus,
    Subject,
    User,
)
from app.policies.academic import (
    can_manage_assessments,
    can_publish_assessment,
    has_own_academics,
    may_read_sections,
    student_sees_assessment,
)
from app.policies.campus import CampusContext
from app.services.academic_setup import audit_academic, current_term
from app.services.attendance import SectionAccess, readable_section
from app.services.notifications import notify_assessment_published, notify_result_revised


@dataclass(frozen=True)
class ScoreInput:
    enrollment_id: uuid.UUID
    score: Decimal | None
    absent: bool

    @property
    def clears(self) -> bool:
        return self.score is None and not self.absent


@dataclass(frozen=True)
class Counts:
    enrolled: int
    entered: int
    absent: int


@dataclass(frozen=True)
class AssessmentView:
    assessment: Assessment
    published_by: tuple[uuid.UUID, str] | None
    counts: Counts
    may_enter_scores: bool
    may_publish: bool


@dataclass(frozen=True)
class ResultRowView:
    enrollment_id: uuid.UUID
    membership_id: uuid.UUID
    display_name: str
    result: AssessmentResult | None


# --- loading -------------------------------------------------------------------------------


def _load_assessment(
    db: Session, campus: CampusContext, assessment_id: uuid.UUID, *, lock: bool = False
) -> Assessment:
    query = select(Assessment).where(
        Assessment.college_id == campus.college_id, Assessment.id == assessment_id
    )
    assessment = db.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if assessment is None:
        raise NotFound()
    return assessment


def _readable_assessment(
    db: Session, campus: CampusContext, assessment_id: uuid.UUID, *, lock: bool = False
) -> tuple[Assessment, SectionAccess]:
    if not may_read_sections(campus):
        raise Forbidden()
    assessment = _load_assessment(db, campus, assessment_id, lock=lock)
    return assessment, readable_section(db, campus, assessment.section_id)


def _enrollment_ids(db: Session, campus: CampusContext, section_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.execute(
            select(Enrollment.id).where(
                Enrollment.college_id == campus.college_id, Enrollment.section_id == section_id
            )
        ).scalars()
    )


def _views(
    db: Session, campus: CampusContext, access: SectionAccess, assessments: list[Assessment]
) -> list[AssessmentView]:
    """Counts for a page of assessments in two queries, whatever the page size."""
    enrolled = len(_enrollment_ids(db, campus, access.section.id))
    ids = [a.id for a in assessments]
    counts: dict[uuid.UUID, tuple[int, int]] = {}
    names: dict[uuid.UUID, str] = {}
    if ids:
        absent = func.count(AssessmentResult.id).filter(AssessmentResult.is_absent)
        counts = {
            assessment_id: (entered, absent_count)
            for assessment_id, entered, absent_count in db.execute(
                select(AssessmentResult.assessment_id, func.count(AssessmentResult.id), absent)
                .where(
                    AssessmentResult.college_id == campus.college_id,
                    AssessmentResult.assessment_id.in_(ids),
                )
                .group_by(AssessmentResult.assessment_id)
            ).all()
        }
        publishers = {a.published_by_membership_id for a in assessments} - {None}
        if publishers:
            names = dict(
                db.execute(
                    select(CollegeMembership.id, User.display_name)
                    .join(User, User.id == CollegeMembership.user_id)
                    .where(
                        CollegeMembership.college_id == campus.college_id,
                        CollegeMembership.id.in_(publishers),
                    )
                ).all()
            )
    manage = can_manage_assessments(campus, access.instructor_ids)
    publish = can_publish_assessment(campus, access.subject.department_id, access.instructor_ids)
    views = []
    for a in assessments:
        entered, absent_count = counts.get(a.id, (0, 0))
        publisher = a.published_by_membership_id
        views.append(
            AssessmentView(
                assessment=a,
                published_by=(publisher, names.get(publisher, "")) if publisher else None,
                counts=Counts(enrolled, entered, absent_count),
                may_enter_scores=manage,
                may_publish=publish and a.published_at is None,
            )
        )
    return views


def _rows(db: Session, campus: CampusContext, assessment: Assessment) -> list[ResultRowView]:
    """Every enrolled student, with their result if entered, by name."""
    rows = db.execute(
        select(Enrollment.id, CollegeMembership.id, User.display_name, AssessmentResult)
        .join(
            CollegeMembership,
            (CollegeMembership.college_id == Enrollment.college_id)
            & (CollegeMembership.id == Enrollment.membership_id),
        )
        .join(User, User.id == CollegeMembership.user_id)
        .outerjoin(
            AssessmentResult,
            (AssessmentResult.college_id == Enrollment.college_id)
            & (AssessmentResult.enrollment_id == Enrollment.id)
            & (AssessmentResult.assessment_id == assessment.id),
        )
        .where(
            Enrollment.college_id == campus.college_id,
            Enrollment.section_id == assessment.section_id,
        )
        .order_by(User.display_name, Enrollment.id)
    ).all()
    return [ResultRowView(e, m, name, result) for e, m, name, result in rows]


# --- the section's assessments (faculty, department admins, college admins) ----------------


def create_assessment(
    db: Session,
    campus: CampusContext,
    section_id: uuid.UUID,
    *,
    name: str,
    kind: str,
    max_score: Decimal,
    held_on: date,
    now: datetime,
) -> AssessmentView:
    access = readable_section(db, campus, section_id)
    if not can_manage_assessments(campus, access.instructor_ids):
        raise Forbidden("Only the section's assigned faculty create assessments.")
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
    assessment = Assessment(
        college_id=campus.college_id,
        section_id=access.section.id,
        name=name,
        kind=kind,
        max_score=max_score,
        held_on=held_on,
        created_by_membership_id=campus.membership.id,
        created_at=now,
        updated_at=now,
    )
    db.add(assessment)
    db.flush()
    audit_academic(
        db,
        campus,
        "assessment_created",
        "assessment",
        assessment.id,
        section_id=str(access.section.id),
    )
    db.commit()
    return _views(db, campus, access, [assessment])[0]


def list_assessments(
    db: Session,
    campus: CampusContext,
    section_id: uuid.UUID,
    *,
    cursor: Cursor | None,
    limit: int,
) -> tuple[list[AssessmentView], str | None]:
    access = readable_section(db, campus, section_id)
    statement = select(Assessment).where(
        Assessment.college_id == campus.college_id, Assessment.section_id == access.section.id
    )
    rows = db.execute(
        newest_first(statement, Assessment.created_at, Assessment.id, cursor, limit)
    ).scalars()
    page, next_cursor = split_page(list(rows), limit, lambda a: (a.created_at, a.id))
    return _views(db, campus, access, page), next_cursor


def get_results(
    db: Session, campus: CampusContext, assessment_id: uuid.UUID
) -> tuple[AssessmentView, list[ResultRowView]]:
    assessment, access = _readable_assessment(db, campus, assessment_id)
    return _views(db, campus, access, [assessment])[0], _rows(db, campus, assessment)


def _check_version(assessment: Assessment, version: int) -> None:
    if assessment.version != version:
        raise Conflict(
            "Someone else changed these results. Reload them and try again.",
            code="version_conflict",
        )


def _check_entries(
    entries: list[ScoreInput], allowed: set[uuid.UUID], max_score: Decimal
) -> dict[uuid.UUID, ScoreInput]:
    problems: list[dict[str, Any]] = []
    found: dict[uuid.UUID, ScoreInput] = {}
    for i, entry in enumerate(entries):
        if entry.enrollment_id not in allowed:
            problems.append(
                {"field": f"results.{i}.enrollment_id", "message": "Not enrolled in this section."}
            )
        elif entry.enrollment_id in found:
            problems.append(
                {"field": f"results.{i}.enrollment_id", "message": "Entered more than once."}
            )
        else:
            found[entry.enrollment_id] = entry
            if entry.score is not None and entry.score > max_score:
                problems.append(
                    {"field": f"results.{i}.score", "message": f"The most is {max_score}."}
                )
    if problems:
        raise ValidationFailed(details=problems)
    return found


def _same(result: AssessmentResult | None, entry: ScoreInput) -> bool:
    if result is None:
        return entry.clears
    return result.is_absent == entry.absent and result.score == entry.score


def save_results(
    db: Session,
    campus: CampusContext,
    assessment_id: uuid.UUID,
    *,
    version: int,
    entries: list[ScoreInput],
    reason: str | None,
    now: datetime,
) -> tuple[AssessmentView, list[ResultRowView]]:
    """ACADEMIC-008, 009, US-07. The assessment row is locked, so two saves from one version
    can't both apply. Only the entries sent are touched."""
    assessment, access = _readable_assessment(db, campus, assessment_id, lock=True)
    if not can_manage_assessments(campus, access.instructor_ids):
        raise Forbidden("Only the section's assigned faculty enter scores.")
    _check_version(assessment, version)
    found = _check_entries(
        entries, _enrollment_ids(db, campus, access.section.id), assessment.max_score
    )
    existing = {
        r.enrollment_id: r
        for r in db.execute(
            select(AssessmentResult).where(
                AssessmentResult.college_id == campus.college_id,
                AssessmentResult.assessment_id == assessment.id,
                AssessmentResult.enrollment_id.in_(found),
            )
        ).scalars()
    }
    changing = {e: entry for e, entry in found.items() if not _same(existing.get(e), entry)}
    published = assessment.published_at is not None
    if published and changing:
        cleared = [
            i for i, entry in enumerate(entries) if entry.enrollment_id in changing and entry.clears
        ]
        if cleared:
            raise ValidationFailed.field(
                f"results.{cleared[0]}.score", "A published result needs a score or ABSENT."
            )
        if not (reason and reason.strip()):
            raise ValidationFailed.field("reason", "Say why the published result changes.")
    if changing:
        for enrollment_id, entry in changing.items():
            result = existing.get(enrollment_id)
            if entry.clears:
                if result is not None:
                    db.delete(result)
                continue
            if result is None:
                result = AssessmentResult(
                    college_id=campus.college_id,
                    assessment_id=assessment.id,
                    enrollment_id=enrollment_id,
                    created_at=now,
                )
                db.add(result)
            else:
                result.version += 1
            result.score = entry.score
            result.is_absent = entry.absent
            result.updated_at = now
            if published:
                result.revised_at = now
        assessment.version += 1
        assessment.updated_at = now
        # ADMIN-006: initial entry isn't audited; changing what was there is, with the
        # students it affects (no values).
        changed = sorted(str(e) for e in changing if e in existing)
        if changed:
            audit_academic(
                db,
                campus,
                "results_changed",
                "assessment",
                assessment.id,
                reason=reason.strip() if reason else None,
                published=published,
                enrollment_ids=changed,
            )
        if published:
            _tell_revised(db, campus, access, assessment, list(changing), now)
    db.commit()
    return _views(db, campus, access, [assessment])[0], _rows(db, campus, assessment)


def _tell_revised(
    db: Session,
    campus: CampusContext,
    access: SectionAccess,
    assessment: Assessment,
    enrollment_ids: list[uuid.UUID],
    now: datetime,
) -> None:
    user_ids = list(
        db.execute(
            select(CollegeMembership.user_id)
            .join(
                Enrollment,
                (Enrollment.college_id == CollegeMembership.college_id)
                & (Enrollment.membership_id == CollegeMembership.id),
            )
            .where(
                Enrollment.college_id == campus.college_id,
                Enrollment.id.in_(enrollment_ids),
                CollegeMembership.status == MembershipStatus.ACTIVE,
            )
        ).scalars()
    )
    notify_result_revised(
        db,
        user_ids=user_ids,
        college_id=campus.college_id,
        assessment_id=assessment.id,
        title=f"Result revised: {access.subject.code} {assessment.name}",
        now=now,
    )


def publish_assessment(
    db: Session, campus: CampusContext, assessment_id: uuid.UUID, *, version: int, now: datetime
) -> AssessmentView:
    """ACADEMIC-009, US-07: once, with every enrolled student scored or ABSENT."""
    assessment, access = _readable_assessment(db, campus, assessment_id, lock=True)
    if not can_publish_assessment(campus, access.subject.department_id, access.instructor_ids):
        raise Forbidden("Only the section's faculty or its department admin publish results.")
    if assessment.published_at is not None:
        raise Conflict("These results are already published.", code="already_published")
    _check_version(assessment, version)
    enrolled = _enrollment_ids(db, campus, access.section.id)
    if not enrolled:
        raise ValidationFailed.field("results", "No students are enrolled in this section yet.")
    entered = db.execute(
        select(func.count(AssessmentResult.id)).where(
            AssessmentResult.college_id == campus.college_id,
            AssessmentResult.assessment_id == assessment.id,
        )
    ).scalar_one()
    if entered < len(enrolled):
        raise ValidationFailed.field(
            "results",
            f"Enter a score or ABSENT for every student ({len(enrolled) - entered} missing).",
        )
    assessment.published_at = now
    assessment.published_by_membership_id = campus.membership.id
    assessment.version += 1
    assessment.updated_at = now
    told = notify_assessment_published(
        db,
        college_id=campus.college_id,
        section_id=access.section.id,
        assessment_id=assessment.id,
        title=f"Results published: {access.subject.code} {assessment.name}",
        now=now,
    )
    audit_academic(db, campus, "assessment_published", "assessment", assessment.id, students=told)
    db.commit()
    return _views(db, campus, access, [assessment])[0]


# --- the student's own results (ACADEMIC-008, US-07, J4) -----------------------------------


@dataclass(frozen=True)
class MyResultView:
    assessment: Assessment
    result: AssessmentResult | None


@dataclass(frozen=True)
class MySubjectView:
    section: ClassSection
    subject: Subject
    results: list[MyResultView]


def my_results(
    db: Session, campus: CampusContext
) -> tuple[AcademicTerm | None, list[MySubjectView]]:
    """Published assessments of the sections the student is enrolled in this term, with their
    own result. Unpublished ones are never selected (ACADEMIC-008)."""
    if not has_own_academics(campus):
        raise Forbidden()
    term = current_term(db, campus.college_id)
    if term is None:
        return None, []
    rows = db.execute(
        select(ClassSection, Subject, Assessment, AssessmentResult)
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
        .join(
            Assessment,
            (Assessment.college_id == ClassSection.college_id)
            & (Assessment.section_id == ClassSection.id),
        )
        .outerjoin(
            AssessmentResult,
            (AssessmentResult.college_id == Assessment.college_id)
            & (AssessmentResult.assessment_id == Assessment.id)
            & (AssessmentResult.enrollment_id == Enrollment.id),
        )
        .where(
            ClassSection.college_id == campus.college_id,
            ClassSection.term_id == term.id,
            Enrollment.membership_id == campus.membership.id,
            Assessment.published_at.is_not(None),
        )
        .order_by(Subject.code, ClassSection.name, Assessment.held_on, Assessment.id)
    ).all()
    grouped: dict[uuid.UUID, MySubjectView] = {}
    for section, subject, assessment, result in rows:
        if not student_sees_assessment(assessment.published_at):  # the query's filter, twice
            continue
        group = grouped.setdefault(section.id, MySubjectView(section, subject, []))
        group.results.append(MyResultView(assessment, result))
    return term, list(grouped.values())
