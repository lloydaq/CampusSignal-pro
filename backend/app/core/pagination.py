"""Cursor pagination for collections (Rules: cursor-based pagination everywhere).

Pages are ordered newest first by (created_at, id); the cursor is the position of the last
item, opaque to clients (base64url of "<iso timestamp>|<uuid>")."""

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, tuple_
from sqlalchemy.orm import InstrumentedAttribute

from app.core.errors import ValidationFailed

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


@dataclass(frozen=True)
class Cursor:
    created_at: datetime
    id: uuid.UUID


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}".encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(value: str | None) -> Cursor | None:
    if value is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()
        stamp, _, row_id = raw.partition("|")
        cursor = Cursor(datetime.fromisoformat(stamp), uuid.UUID(row_id))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise ValidationFailed.field("cursor", "This cursor isn't valid.") from None
    if cursor.created_at.tzinfo is None:
        raise ValidationFailed.field("cursor", "This cursor isn't valid.")
    return cursor


def newest_first[S: Select[Any]](
    query: S,
    created_at: InstrumentedAttribute[datetime],
    row_id: InstrumentedAttribute[uuid.UUID],
    cursor: Cursor | None,
    limit: int,
) -> S:
    """Apply ordering, the cursor and limit+1 (the extra row tells whether a next page exists)."""
    if cursor is not None:
        query = query.where(tuple_(created_at, row_id) < tuple_(cursor.created_at, cursor.id))
    return query.order_by(created_at.desc(), row_id.desc()).limit(limit + 1)


def split_page[T](rows: list[T], limit: int, key: Any) -> tuple[list[T], str | None]:
    """The page's items and the next cursor (None on the last page). `key(row)` returns the
    row's (created_at, id)."""
    if len(rows) <= limit:
        return rows, None
    items = rows[:limit]
    created_at, row_id = key(items[-1])
    return items, encode_cursor(created_at, row_id)
