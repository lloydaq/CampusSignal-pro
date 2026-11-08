"""Academic setup decisions (ACADEMIC-001…004, 010; PRD §11). Pure functions over loaded rows.

Deny shape (Rules R-2.4): someone with no academic role at all gets 403 from the service; someone
with a role who asks about an object outside it (another department's subject, a section they
don't teach) gets 404, the same answer as for an object that doesn't exist.
"""

import uuid
from collections.abc import Iterable

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
