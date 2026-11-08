"""The role-aware home (HOME-001…004, US-16): blocks composed from the module services, so the
home can show nothing those modules' own endpoints wouldn't (HOME-004).

Each block runs in its own savepoint; one that fails comes back as an error block and the others
still render (US-16: "a failing block does not hide other blocks"). Which blocks appear depends
on who is asking: a block the viewer can't use is left out, not shown empty.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicTerm, AttendanceSession, ClassSection, Subject
from app.policies.academic import has_own_academics, is_teacher
from app.policies.campus import CampusContext, can_view_directory
from app.policies.community import can_see_moderation_queue
from app.policies.issues import can_see_queue
from app.services import academic_setup, attendance, membership_requests, moderation
from app.services.issues import service as issues

log = logging.getLogger(__name__)

NEEDS_ATTENDANCE_DAYS = 7  # HOME-002
MY_ISSUES_SHOWN = 3


@dataclass
class Block:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Missing:
    """A timetabled class with no attendance recorded for its section that day."""

    section: ClassSection
    subject: Subject
    held_on: date
    starts_at: Any


def _run(db: Session, name: str, build: Callable[[], dict[str, Any]]) -> Block:
    try:
        with db.begin_nested():
            return Block(True, build())
    except Exception:
        # Only the block's name: never its data (Rules R-2.11).
        log.exception("home block failed", extra={"block": name})
        return Block(False)


def college_now(campus: CampusContext, now: datetime) -> datetime:
    return now.astimezone(ZoneInfo(campus.college.timezone))


def _today_classes(rows: list[academic_setup.MyClassRow], today: date) -> list[Any]:
    weekday = today.isoweekday()
    return [r for r in rows if r.entry.weekday == weekday]


def _needs_attendance(
    db: Session,
    campus: CampusContext,
    term: AcademicTerm,
    rows: list[academic_setup.MyClassRow],
    local_now: datetime,
) -> list[Missing]:
    """HOME-002: classes in the last 7 days (inside the term, already over) whose section has no
    session recorded that day."""
    today = local_now.date()
    first = max(today - timedelta(days=NEEDS_ATTENDANCE_DAYS - 1), term.starts_on)
    last = min(today, term.ends_on)
    if first > last or not rows:
        return []
    sections = {r.section.id for r in rows}
    recorded = set(
        db.execute(
            select(AttendanceSession.section_id, AttendanceSession.held_on).where(
                AttendanceSession.college_id == campus.college_id,
                AttendanceSession.section_id.in_(sections),
                AttendanceSession.held_on.between(first, last),
            )
        ).all()
    )
    missing: dict[tuple[uuid.UUID, date], Missing] = {}
    day = first
    while day <= last:
        for r in rows:
            if r.entry.weekday != day.isoweekday() or (r.section.id, day) in recorded:
                continue
            if day == today and r.entry.ends_at > local_now.time():
                continue  # the class hasn't finished yet
            key = (r.section.id, day)
            if key not in missing:
                missing[key] = Missing(r.section, r.subject, day, r.entry.starts_at)
        day += timedelta(days=1)
    return sorted(missing.values(), key=lambda m: (m.held_on, m.starts_at), reverse=True)


def home(db: Session, campus: CampusContext, now: datetime) -> dict[str, Block]:
    """The blocks for this viewer, by name."""
    local_now = college_now(campus, now)
    today = local_now.date()
    blocks: dict[str, Block] = {}

    if has_own_academics(campus):

        def classes() -> dict[str, Any]:
            term, rows = academic_setup.my_timetable(db, campus)
            return {"term": term, "items": _today_classes(rows, today)}

        def attendance_block() -> dict[str, Any]:
            term, rows = attendance.my_attendance(db, campus)
            return {"term": term, "items": rows}

        blocks["classes"] = _run(db, "classes", classes)
        blocks["attendance"] = _run(db, "attendance", attendance_block)

    if is_teacher(campus):

        def teaching_classes() -> dict[str, Any]:
            term, rows = academic_setup.teaching_timetable(db, campus)
            return {"term": term, "items": _today_classes(rows, today)}

        def needs_attendance() -> dict[str, Any]:
            term, rows = academic_setup.teaching_timetable(db, campus)
            items = _needs_attendance(db, campus, term, rows, local_now) if term else []
            return {"term": term, "items": items}

        blocks["classes"] = _run(db, "classes", teaching_classes)
        blocks["needs_attendance"] = _run(db, "needs_attendance", needs_attendance)

    def my_issues() -> dict[str, Any]:
        items, count = issues.my_open_issues(db, campus, limit=MY_ISSUES_SHOWN)
        return {"items": items, "open_count": count}

    blocks["my_issues"] = _run(db, "my_issues", my_issues)

    # HOME-003: only the queues the viewer can act on.
    queues: list[tuple[str, Callable[[], int]]] = []
    if can_view_directory(campus):
        queues.append(
            ("membership_requests", lambda: membership_requests.pending_count(db, campus))
        )
    if can_see_moderation_queue(campus):
        queues.append(("content_reports", lambda: moderation.open_report_count(db, campus)))
    if can_see_queue(campus):
        queues.append(("unacknowledged_issues", lambda: issues.unacknowledged_count(db, campus)))
    if queues:
        blocks["queues"] = _run(
            db, "queues", lambda: {"items": [(kind, count()) for kind, count in queues]}
        )
    return blocks
