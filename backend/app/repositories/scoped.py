"""Base helpers for college-scoped tables (architecture.md §9, TENANT-002)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import Base
from app.core.errors import NotFound


def get_in_college[T: Base](
    db: Session, model: type[T], college_id: uuid.UUID, object_id: uuid.UUID
) -> T:
    """The row with this id *in this college*, else NotFound (404). A row of another college
    is indistinguishable from one that doesn't exist."""
    columns = model.__table__.c
    row = db.execute(
        select(model).where(columns.id == object_id, columns.college_id == college_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFound()
    return row
