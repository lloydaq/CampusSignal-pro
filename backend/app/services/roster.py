"""Roster import and listing (MEMBER-001). College admins only.

The CSV is validated completely before anything is written; any problem rejects the whole
file and every problem is reported with its row and column (all-or-nothing). Roll numbers are
stored upper-cased so later matching (3d) doesn't depend on how they were typed.
"""

import csv
import io
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, ValidationFailed
from app.core.pagination import Cursor, newest_first, split_page
from app.models import CollegeMembership, Department, MembershipStatus, RosterEntry
from app.policies.campus import CampusContext
from app.schemas.auth import EMAIL_MAX_LENGTH
from app.services.audit import record_audit
from app.services.departments import require_college_admin

COLUMNS = ("roll_number", "full_name", "department_code", "program", "admission_year", "email")
MAX_ROWS = 5000
MAX_REPORTED_PROBLEMS = 200
ACTION_ROSTER_IMPORTED = "college.roster_imported"

ROLL_NUMBER = re.compile(r"^[A-Z0-9][A-Z0-9/._-]{0,39}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


class RosterInvalid(ValidationFailed):
    code = "roster_invalid"
    default_message = "The roster file has problems. Nothing was imported."


@dataclass(frozen=True)
class Problem:
    row: int
    column: str | None
    message: str

    def as_detail(self) -> dict[str, Any]:
        return {"row": self.row, "column": self.column, "message": self.message}


def _file_problem(message: str) -> RosterInvalid:
    return RosterInvalid(details=[Problem(1, None, message).as_detail()])


def _clean_text(value: str, limit: int) -> str | None:
    value = " ".join(value.split())
    return value if 1 <= len(value) <= limit and value.isprintable() else None


def import_roster(db: Session, campus: CampusContext, *, text: str, now: datetime) -> int:
    require_college_admin(campus)
    if not text.strip():
        raise _file_problem("The file is empty.")
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    if sorted(header) != sorted(COLUMNS):
        raise _file_problem(f"The header must have exactly these columns: {', '.join(COLUMNS)}.")
    reader.fieldnames = header

    departments = {
        d.code: d
        for d in db.execute(
            select(Department).where(
                Department.college_id == campus.college_id, Department.archived_at.is_(None)
            )
        ).scalars()
    }
    existing = set(
        db.execute(
            select(RosterEntry.roll_number).where(RosterEntry.college_id == campus.college_id)
        ).scalars()
    )

    problems: list[Problem] = []
    entries: list[RosterEntry] = []
    seen: set[str] = set()
    for raw in reader:
        row = reader.line_num
        if all(not (v or "").strip() for k, v in raw.items() if k is not None):
            continue  # blank line
        if len(entries) + len(problems) >= MAX_ROWS:
            raise _file_problem(f"Import at most {MAX_ROWS} rows at a time.")

        def get(column: str, row_data: dict[str | Any, str | None] = raw) -> str:
            return (row_data.get(column) or "").strip()

        row_problems: list[Problem] = []
        roll = get("roll_number").upper()
        if not ROLL_NUMBER.match(roll):
            row_problems.append(
                Problem(row, "roll_number", "Use 1 to 40 letters, digits or / . _ -.")
            )
        elif roll in existing:
            row_problems.append(Problem(row, "roll_number", "Already on the roster."))
        elif roll in seen:
            row_problems.append(Problem(row, "roll_number", "Appears twice in this file."))
        full_name = _clean_text(get("full_name"), 120)
        if full_name is None:
            row_problems.append(Problem(row, "full_name", "Use 1 to 120 characters."))
        department = departments.get(get("department_code").upper())
        if department is None:
            row_problems.append(
                Problem(row, "department_code", "No current department has this code.")
            )
        program = _clean_text(get("program"), 120)
        if program is None:
            row_problems.append(Problem(row, "program", "Use 1 to 120 characters."))
        year_text = get("admission_year")
        year = int(year_text) if year_text.isdigit() else None
        if year is None or not 1900 <= year <= 2200:
            row_problems.append(Problem(row, "admission_year", "Use a year such as 2025."))
        email = get("email").lower() or None
        if email is not None and (len(email) > EMAIL_MAX_LENGTH or not _EMAIL.match(email)):
            row_problems.append(
                Problem(row, "email", "Enter a valid email address or leave it empty.")
            )

        seen.add(roll)
        problems.extend(row_problems)
        if row_problems or department is None or not (full_name and program and year):
            continue
        entries.append(
            RosterEntry(
                college_id=campus.college_id,
                department_id=department.id,
                roll_number=roll,
                full_name=full_name,
                email=email,
                program=program,
                admission_year=year,
                created_at=now,
            )
        )

    if problems:
        raise RosterInvalid(details=[p.as_detail() for p in problems[:MAX_REPORTED_PROBLEMS]])
    if not entries:
        raise _file_problem("The file has no rows to import.")
    try:
        with db.begin_nested():
            db.add_all(entries)
            db.flush()
    except IntegrityError:
        raise Conflict(
            "The roster changed while importing. Try again.", code="roster_conflict"
        ) from None
    record_audit(
        db,
        action=ACTION_ROSTER_IMPORTED,
        actor_user_id=campus.user.id,
        college_id=campus.college_id,
        target_type="roster",
        metadata={"rows": len(entries)},
    )
    db.commit()
    return len(entries)


@dataclass(frozen=True)
class RosterRow:
    entry: RosterEntry
    department: Department
    claimed: bool


def list_roster(
    db: Session,
    campus: CampusContext,
    *,
    query: str | None,
    department_id: uuid.UUID | None,
    cursor: Cursor | None,
    limit: int,
) -> tuple[list[RosterRow], str | None]:
    require_college_admin(campus)
    claimed = exists().where(
        CollegeMembership.college_id == RosterEntry.college_id,
        CollegeMembership.roster_entry_id == RosterEntry.id,
        CollegeMembership.status == MembershipStatus.ACTIVE,
    )
    statement = (
        select(RosterEntry, Department, claimed)
        .join(
            Department,
            (Department.college_id == RosterEntry.college_id)
            & (Department.id == RosterEntry.department_id),
        )
        .where(RosterEntry.college_id == campus.college_id)
    )
    if query:
        statement = statement.where(
            RosterEntry.roll_number.icontains(query, autoescape=True)
            | RosterEntry.full_name.icontains(query, autoescape=True)
        )
    if department_id is not None:
        statement = statement.where(RosterEntry.department_id == department_id)
    rows = db.execute(
        newest_first(statement, RosterEntry.created_at, RosterEntry.id, cursor, limit)
    ).all()
    page, next_cursor = split_page(list(rows), limit, lambda r: (r[0].created_at, r[0].id))
    return [
        RosterRow(entry, department, bool(is_claimed)) for entry, department, is_claimed in page
    ], next_cursor
