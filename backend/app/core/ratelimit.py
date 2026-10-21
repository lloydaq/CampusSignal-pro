"""Fixed-window rate limits stored in PostgreSQL (architecture.md §10, ADR-05).

Counters live in `rate_limit_counters`, so limits hold across workers without Redis.
Keys that identify people (emails) are hashed before storage. A window's counter is
created or incremented atomically with INSERT ... ON CONFLICT DO UPDATE.
"""

import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.rate_limit import RateLimitCounter


@dataclass(frozen=True)
class Limit:
    name: str
    max_hits: int
    window: timedelta


@dataclass(frozen=True)
class RateLimitState:
    count: int
    limit: Limit
    retry_after_seconds: int

    @property
    def exceeded(self) -> bool:
        return self.count >= self.limit.max_hits


def hashed_key(value: str) -> str:
    """Stable, non-reversible key for personal values such as normalised emails."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _window_start(limit: Limit, now: datetime) -> datetime:
    seconds = int(limit.window.total_seconds())
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, tz=UTC)


def _state(limit: Limit, count: int, start: datetime, now: datetime) -> RateLimitState:
    retry = math.ceil((start + limit.window - now).total_seconds())
    return RateLimitState(count=count, limit=limit, retry_after_seconds=max(retry, 1))


def current(session: Session, limit: Limit, key: str, now: datetime) -> RateLimitState:
    """Hits recorded in the current window, without recording a new one."""
    start = _window_start(limit, now)
    count = session.execute(
        select(RateLimitCounter.count).where(
            RateLimitCounter.bucket_key == f"{limit.name}:{key}",
            RateLimitCounter.window_start == start,
        )
    ).scalar_one_or_none()
    return _state(limit, count or 0, start, now)


def hit(session: Session, limit: Limit, key: str, now: datetime) -> RateLimitState:
    """Record one hit in the current window and return the new state."""
    start = _window_start(limit, now)
    stmt = (
        insert(RateLimitCounter)
        .values(bucket_key=f"{limit.name}:{key}", window_start=start, count=1)
        .on_conflict_do_update(
            index_elements=[RateLimitCounter.bucket_key, RateLimitCounter.window_start],
            set_={"count": RateLimitCounter.count + 1},
        )
        .returning(RateLimitCounter.count)
    )
    count = session.execute(stmt).scalar_one()
    return _state(limit, count, start, now)
