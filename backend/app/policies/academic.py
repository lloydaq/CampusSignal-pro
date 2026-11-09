"""Academic setup decisions (ACADEMIC-001…004, 010; PRD §11). Pure functions over loaded rows.

Deny shape (Rules R-2.4): someone with no academic role at all gets 403 from the service; someone
with a role who asks about an object outside it (another department's subject, a section they
don't teach) gets 404, the same answer as for an object that doesn't exist.
"""

import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta
from enum import StrEnum

from app.models import CollegeMembership, MembershipKind, MembershipStatus
from app.policies.campus import CampusContext, administered_departments, is_college_admin

NOT_ACTIVE_FACULTY = "not_active_faculty"
NOT_ACTIVE_STUDENT = "not_active_student"


def can_manage_terms(campus: CampusContext) -> bool:
    """ACADEMIC-001: college admins manage terms."""
    return is_college_admin(campus.grants)


def manages_any_catalog(campus: CampusContext) -> bool:
    """College admins, and department admins of at least one department, manage subjects,
    sections, instructors, enrollment and the timetable (ACADEMIC-002, 003)."""
    return is_college_admin(campus.grants) or bool(administered_departments(campus.grants))


def can_manage_catalog(campus: CampusContext, department_id: uuid.UUID) -> bool:
    """For subjects of `department_id` and everything hanging off them (their sections,
    instructors, enrollments, timetable entries)."""
    return is_college_admin(campus.grants) or department_id in administered_departments(
        campus.grants
    )


def managed_departments(campus: CampusContext) -> frozenset[uuid.UUID] | None:
    """Departments whose catalog `campus` manages; None means every department."""
    if is_college_admin(campus.grants):
        return None
    return administered_departments(campus.grants)


def is_teacher(campus: CampusContext) -> bool:
    return campus.membership.kind == MembershipKind.FACULTY


def has_own_academics(campus: CampusContext) -> bool:
    """Only students have a timetable, attendance and results of their own (PRD §11)."""
    return campus.membership.kind == MembershipKind.STUDENT


def may_read_sections(campus: CampusContext) -> bool:
    """Who may ask about sections at all: catalog managers and faculty."""
    return manages_any_catalog(campus) or is_teacher(campus)


def can_read_section(
    campus: CampusContext, department_id: uuid.UUID, instructor_ids: Iterable[uuid.UUID]
) -> bool:
    """ACADEMIC-010: the section's department's managers, and its assigned faculty."""
    if can_manage_catalog(campus, department_id):
        return True
    return is_teacher(campus) and campus.membership.id in set(instructor_ids)


def instructor_problem(member: CollegeMembership) -> str | None:
    """ACADEMIC-002: only ACTIVE faculty of the same college teach sections (the caller has
    already loaded `member` inside the acting college)."""
    if member.kind != MembershipKind.FACULTY or member.status != MembershipStatus.ACTIVE:
        return NOT_ACTIVE_FACULTY
    return None


def enrollment_problem(member: CollegeMembership) -> str | None:
    """ACADEMIC-002: only ACTIVE students of the same college are enrolled."""
    if member.kind != MembershipKind.STUDENT or member.status != MembershipStatus.ACTIVE:
        return NOT_ACTIVE_STUDENT
    return None


# --- attendance (ACADEMIC-005, 006) --------------------------------------------------------


def is_assigned_teacher(campus: CampusContext, instructor_ids: Iterable[uuid.UUID]) -> bool:
    return is_teacher(campus) and campus.membership.id in set(instructor_ids)


def can_record_attendance(campus: CampusContext, instructor_ids: Iterable[uuid.UUID]) -> bool:
    """ACADEMIC-005: only the section's assigned faculty record a session."""
    return is_assigned_teacher(campus, instructor_ids)


def edit_window_open(created_at: datetime, window_hours: int, now: datetime) -> bool:
    """ACADEMIC-006 / P-5: faculty may edit a session until `window_hours` after it was
    recorded (the college's setting, 48 by default)."""
    return now < created_at + timedelta(hours=window_hours)


class AttendanceEdit(StrEnum):
    FACULTY = "faculty"  # the assigned teacher, inside the window; a reason is optional
    CORRECTION = "correction"  # a department admin of the section's department; reason required
    WINDOW_CLOSED = "window_closed"  # the assigned teacher, too late: 403


def attendance_edit(
    campus: CampusContext,
    department_id: uuid.UUID,
    instructor_ids: Iterable[uuid.UUID],
    *,
    created_at: datetime,
    window_hours: int,
    now: datetime,
) -> AttendanceEdit | None:
    """How `campus` may edit a session of a section in `department_id`, or None if not at all.
    College admins don't record or correct attendance (PRD §11); they only read it."""
    teacher = is_assigned_teacher(campus, instructor_ids)
    if teacher and edit_window_open(created_at, window_hours, now):
        return AttendanceEdit.FACULTY
    if department_id in administered_departments(campus.grants):
        return AttendanceEdit.CORRECTION
    if teacher:
        return AttendanceEdit.WINDOW_CLOSED
    return None


def attendance_percentage(held: int, attended: int, excused: int) -> float | None:
    """ACADEMIC-007: EXCUSED sessions leave the denominator. None when nothing counts yet."""
    counted = held - excused
    if counted <= 0:
        return None
    return round(100 * attended / counted, 1)


# --- assessments and results (ACADEMIC-008, 009) -------------------------------------------


def can_manage_assessments(campus: CampusContext, instructor_ids: Iterable[uuid.UUID]) -> bool:
    """ACADEMIC-008: the section's assigned faculty create assessments and enter scores, before
    and after publishing (owner decision 2026-11-08: department admins don't change scores)."""
    return is_assigned_teacher(campus, instructor_ids)


def can_publish_assessment(
    campus: CampusContext, department_id: uuid.UUID, instructor_ids: Iterable[uuid.UUID]
) -> bool:
    """ACADEMIC-009: the section's assigned faculty, or a department admin of its department.
    College admins read results but don't publish them (PRD §11)."""
    return is_assigned_teacher(campus, instructor_ids) or department_id in administered_departments(
        campus.grants
    )


def student_sees_assessment(published_at: datetime | None) -> bool:
    """ACADEMIC-008: nothing about an assessment reaches students before it's published."""
    return published_at is not None
