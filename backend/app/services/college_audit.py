"""A college's audit log for its college admins (ADMIN-007). Only entries with this college's
id are ever read (US-14)."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden
from app.core.pagination import Cursor, newest_first, split_page
from app.models import AuditLog
from app.models.user import User
from app.policies.campus import CampusContext, can_manage_college


def college_audit(
    db: Session,
    campus: CampusContext,
    *,
    action: str | None,
    actor_user_id: uuid.UUID | None,
    since: datetime | None,
    until: datetime | None,
    cursor: Cursor | None,
    limit: int,
) -> tuple[list[tuple[AuditLog, User | None]], str | None]:
    if not can_manage_college(campus):
        raise Forbidden()
    statement = (
        select(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(AuditLog.college_id == campus.college_id)
    )
    if action:
        statement = statement.where(AuditLog.action == action)
    if actor_user_id:
        statement = statement.where(AuditLog.actor_user_id == actor_user_id)
    if since:
        statement = statement.where(AuditLog.created_at >= since)
    if until:
        statement = statement.where(AuditLog.created_at < until)
    rows = db.execute(
        newest_first(statement, AuditLog.created_at, AuditLog.id, cursor, limit)
    ).all()
    page, next_cursor = split_page(list(rows), limit, lambda r: (r[0].created_at, r[0].id))
    return [(entry, user) for entry, user in page], next_cursor
