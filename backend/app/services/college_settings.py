"""College settings (ACADEMIC-006, P-5): for now the attendance edit window, which faculty
edits are measured against for every session, recorded before or after the change. College
admins only; each change is audited with the old and new value."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden
from app.models import College
from app.policies.campus import CampusContext, can_manage_college
from app.services.audit import record_audit

ACTION_SETTINGS_CHANGED = "college.settings_changed"


def get_settings(campus: CampusContext) -> College:
    if not can_manage_college(campus):
        raise Forbidden()
    return campus.college


def update_settings(db: Session, campus: CampusContext, *, edit_window_hours: int) -> College:
    if not can_manage_college(campus):
        raise Forbidden()
    college = db.execute(
        select(College).where(College.id == campus.college_id).with_for_update()
    ).scalar_one()
    previous = college.attendance_edit_window_hours
    if previous != edit_window_hours:
        college.attendance_edit_window_hours = edit_window_hours
        record_audit(
            db,
            action=ACTION_SETTINGS_CHANGED,
            actor_user_id=campus.user.id,
            college_id=campus.college_id,
            target_type="college",
            target_id=str(campus.college_id),
            metadata={
                "setting": "attendance_edit_window_hours",
                "from": previous,
                "to": edit_window_hours,
            },
        )
    db.commit()
    return college
