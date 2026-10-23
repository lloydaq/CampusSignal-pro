"""Retention purges run by the Jobs CLI (architecture.md §8.3, ADR-07).

Each purge deletes only rows that are already dead or past retention, so running it again
deletes nothing new. Each runs and commits in its own transaction. Notifications (90 days)
join here when that table arrives in Phase 4.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, Delete, delete, or_, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.audit import AuditLog
from app.models.auth_session import AuthSession
from app.models.rate_limit import RateLimitCounter
from app.models.user_token import UserToken

TOKEN_GRACE = timedelta(days=7)
RATE_COUNTER_MAX_AGE = timedelta(days=1)  # every rate window is at most an hour
# [Assumption, PRD §21 item 10] Audit entries are kept 2 years.
AUDIT_RETENTION = timedelta(days=730)


def _deleted(db: Session, statement: Delete) -> int:
    # A DELETE always returns a CursorResult, which carries the row count.
    result = cast(CursorResult[Any], db.execute(statement))
    return result.rowcount


def purge_sessions(db: Session, settings: Settings, now: datetime) -> int:
    """Sessions that can no longer be used. Uses the looser (non-privileged) limits, so a
    privileged session past its shorter limit waits for its expires_at or is deleted on
    sight by `load_session`; nothing still valid is ever removed."""
    idle_cutoff = now - timedelta(days=settings.session_idle_days)
    absolute_cutoff = now - timedelta(days=settings.session_absolute_days)
    return _deleted(
        db,
        delete(AuthSession).where(
            or_(
                AuthSession.expires_at <= now,
                AuthSession.last_seen_at <= idle_cutoff,
                AuthSession.created_at <= absolute_cutoff,
            )
        ),
    )


def purge_tokens(db: Session, settings: Settings, now: datetime) -> int:
    return _deleted(db, delete(UserToken).where(UserToken.expires_at <= now - TOKEN_GRACE))


def purge_rate_limit_counters(db: Session, settings: Settings, now: datetime) -> int:
    return _deleted(
        db,
        delete(RateLimitCounter).where(RateLimitCounter.window_start <= now - RATE_COUNTER_MAX_AGE),
    )


def purge_audit_log(db: Session, settings: Settings, now: datetime) -> int:
    # The append-only trigger (migration 0003) allows DELETE only while this
    # transaction-local flag is on; it resets at commit or rollback.
    db.execute(text("SELECT set_config('campussignal.audit_purge', 'on', true)"))
    return _deleted(db, delete(AuditLog).where(AuditLog.created_at < now - AUDIT_RETENTION))


Purge = Callable[[Session, Settings, datetime], int]

PURGES: dict[str, Purge] = {
    "sessions": purge_sessions,
    "user_tokens": purge_tokens,
    "rate_limit_counters": purge_rate_limit_counters,
    "audit_log": purge_audit_log,
}


@dataclass(frozen=True)
class PurgeOutcome:
    name: str
    deleted: int | None  # None when the purge failed and was rolled back
    error_type: str | None = None


def run_purges(
    session_factory: Callable[[], Session], settings: Settings, now: datetime
) -> list[PurgeOutcome]:
    """Run every purge in its own transaction. A failing purge is rolled back and reported;
    the others still run."""
    outcomes: list[PurgeOutcome] = []
    for name, purge in PURGES.items():
        with session_factory() as db:
            try:
                deleted = purge(db, settings, now)
                db.commit()
            except Exception as exc:
                db.rollback()
                outcomes.append(PurgeOutcome(name, None, type(exc).__name__))
                continue
        outcomes.append(PurgeOutcome(name, deleted))
    return outcomes
