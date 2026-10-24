"""Notice decisions (NOTICE-002, 004, 006, DEPT-004). Pure functions over loaded rows.

Who may publish where, who may change a notice, who may read it. Lists filter in SQL, so the
same rules are also exposed as audiences (which departments' notices, whether college notices);
a test keeps the audiences and `can_read_notice` in agreement, so a list can never show what
the single-notice route would refuse.
"""

import uuid
from dataclasses import dataclass

from app.models import Notice, NoticeScope, NoticeStatus
from app.policies.campus import CampusContext, administered_departments, is_college_admin


@dataclass(frozen=True)
class DepartmentAudience:
    """Which departments' notices someone may see: every department, or just these."""

    every_department: bool
    department_ids: frozenset[uuid.UUID] = frozenset()

    def includes(self, department_id: uuid.UUID) -> bool:
        return self.every_department or department_id in self.department_ids


@dataclass(frozen=True)
class ManagedAudience:
    """The notices someone may edit, publish or withdraw: college notices (or not) and some
    departments' notices."""

    include_college: bool
    departments: DepartmentAudience


def can_publish_notices(campus: CampusContext) -> bool:
    """NOTICE-002: only college admins and department admins publish anything."""
    return is_college_admin(campus.grants) or bool(administered_departments(campus.grants))


def can_publish_in(campus: CampusContext, scope: str, department_id: uuid.UUID | None) -> bool:
    """College admins publish college-wide and for any department; a department admin only for
    a department they administer (never college-wide)."""
    if is_college_admin(campus.grants):
        return True
    if scope == NoticeScope.COLLEGE or department_id is None:
        return False
    return department_id in administered_departments(campus.grants)


def can_manage_notice(campus: CampusContext, notice: Notice) -> bool:
    """NOTICE-006: whoever can publish in a notice's scope can edit, publish and withdraw it.
    The author is one of them only while they still hold the role."""
    return can_publish_in(campus, notice.scope, notice.department_id)


def managed_audience(campus: CampusContext) -> ManagedAudience:
    if is_college_admin(campus.grants):
        return ManagedAudience(True, DepartmentAudience(True))
    return ManagedAudience(
        False, DepartmentAudience(False, administered_departments(campus.grants))
    )


def published_audience(campus: CampusContext) -> DepartmentAudience:
    """NOTICE-004: published department notices reach the department's members, college admins
    and the department's admins. (College notices reach every ACTIVE member.)"""
    if is_college_admin(campus.grants):
        return DepartmentAudience(True)
    departments = set(administered_departments(campus.grants))
    if campus.membership.department_id is not None:
        departments.add(campus.membership.department_id)
    return DepartmentAudience(False, frozenset(departments))


def can_read_notice(campus: CampusContext, notice: Notice) -> bool:
    if notice.status == NoticeStatus.PUBLISHED:
        if notice.scope == NoticeScope.COLLEGE:
            return True
        return notice.department_id is not None and published_audience(campus).includes(
            notice.department_id
        )
    # Drafts and withdrawn notices belong to the people who may manage them.
    return can_manage_notice(campus, notice)


def can_edit_department_description(campus: CampusContext, department_id: uuid.UUID) -> bool:
    """DEPT-004: college admins, and a department admin for their own department."""
    return is_college_admin(campus.grants) or department_id in administered_departments(
        campus.grants
    )
