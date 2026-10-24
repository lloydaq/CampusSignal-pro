"""Departments (DEPT-001). College admins manage them; members list them."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound
from app.models import Department
from app.policies.campus import CampusContext, administered_departments, can_manage_college
from app.policies.notices import can_edit_department_description
from app.repositories.scoped import get_in_college
from app.services.audit import record_audit

ACTION_DEPARTMENT_CREATED = "college.department_created"
ACTION_DEPARTMENT_UPDATED = "college.department_updated"


def require_college_admin(campus: CampusContext) -> None:
    if not can_manage_college(campus):
        raise Forbidden()


def list_departments(
    db: Session, campus: CampusContext, *, include_archived: bool
) -> list[Department]:
    query = select(Department).where(Department.college_id == campus.college_id)
    # Archived departments are an admin concern; members only see current ones.
    if not (include_archived and can_manage_college(campus)):
        query = query.where(Department.archived_at.is_(None))
    return list(db.execute(query.order_by(Department.code)).scalars())


def get_department(db: Session, campus: CampusContext, department_id: uuid.UUID) -> Department:
    return get_in_college(db, Department, campus.college_id, department_id)


def create_department(
    db: Session, campus: CampusContext, *, code: str, name: str, description: str, now: datetime
) -> Department:
    require_college_admin(campus)
    department = Department(
        college_id=campus.college_id,
        code=code,
        name=name,
        description=description,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(department)
            db.flush()
    except IntegrityError:
        raise Conflict("A department with this code already exists.", code="code_taken") from None
    record_audit(
        db,
        action=ACTION_DEPARTMENT_CREATED,
        actor_user_id=campus.user.id,
        college_id=campus.college_id,
        target_type="department",
        target_id=str(department.id),
        metadata={"code": code},
    )
    db.commit()
    return department


def update_department(
    db: Session,
    campus: CampusContext,
    department_id: uuid.UUID,
    *,
    name: str | None,
    description: str | None,
    archived: bool | None,
    now: datetime,
) -> Department:
    department = get_in_college(db, Department, campus.college_id, department_id)
    if not can_manage_college(campus):
        # DEPT-004: a department admin edits only their own department's description.
        if not administered_departments(campus.grants):
            raise Forbidden()
        if not can_edit_department_description(campus, department.id):
            raise NotFound()
        if name is not None or archived is not None:
            raise Forbidden()
    changed: list[str] = []
    if name is not None and name != department.name:
        department.name = name
        changed.append("name")
    if description is not None and description != department.description:
        department.description = description
        changed.append("description")
    if archived is not None and archived != (department.archived_at is not None):
        department.archived_at = now if archived else None
        changed.append("archived" if archived else "unarchived")
    if changed:
        department.updated_at = now
        record_audit(
            db,
            action=ACTION_DEPARTMENT_UPDATED,
            actor_user_id=campus.user.id,
            college_id=campus.college_id,
            target_type="department",
            target_id=str(department.id),
            metadata={"changes": changed},
        )
    db.commit()
    return department
