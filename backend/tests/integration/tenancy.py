"""Two-college fixtures for tenant isolation tests (CLAUDE.md: "Northfield Institute" and
"Riverside College"). Rows are added straight to the database; the API under test reads them.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    College,
    CollegeMembership,
    CollegeStatus,
    Department,
    MembershipKind,
    MembershipStatus,
    Role,
    RoleGrant,
    RosterEntry,
    User,
)

PASSWORD = "tidal-quartz-lantern"
_HASH: dict[str, str] = {}


@dataclass
class Campus:
    college: College
    departments: dict[str, Department] = field(default_factory=dict)

    @property
    def id(self) -> uuid.UUID:
        return self.college.id


def make_college(
    session: Session,
    name: str,
    slug: str,
    *,
    status: CollegeStatus = CollegeStatus.ACTIVE,
    departments: tuple[str, ...] = ("CSE", "MECH"),
) -> Campus:
    college = College(name=name, slug=slug, timezone="Asia/Kolkata", status=status)
    session.add(college)
    session.flush()
    campus = Campus(college)
    for code in departments:
        department = Department(college_id=college.id, code=code, name=f"{code} department")
        session.add(department)
        campus.departments[code] = department
    session.flush()
    return campus


def two_colleges(session: Session) -> tuple[Campus, Campus]:
    return (
        make_college(session, "Northfield Institute", "northfield"),
        make_college(session, "Riverside College", "riverside"),
    )


def make_user(
    session: Session,
    email: str,
    *,
    name: str = "Test Person",
    verified: bool = True,
    platform_admin: bool = False,
) -> User:
    if PASSWORD not in _HASH:  # Argon2 is slow on purpose; hash once per test run
        _HASH[PASSWORD] = hash_password(PASSWORD)
    user = User(
        email=email,
        password_hash=_HASH[PASSWORD],
        display_name=name,
        email_verified_at=datetime(2026, 10, 1, tzinfo=UTC) if verified else None,
        platform_role="PLATFORM_ADMIN" if platform_admin else None,
    )
    session.add(user)
    session.flush()
    return user


def add_member(
    session: Session,
    user: User,
    campus: Campus,
    kind: MembershipKind = MembershipKind.STUDENT,
    *,
    status: MembershipStatus = MembershipStatus.ACTIVE,
    department: str | None = "CSE",
    roles: tuple[tuple[Role, str | None], ...] = (),
) -> CollegeMembership:
    membership = CollegeMembership(
        user_id=user.id,
        college_id=campus.id,
        kind=kind,
        status=status,
        department_id=campus.departments[department].id if department else None,
    )
    session.add(membership)
    session.flush()
    for role, department_code in roles:
        grant(
            session,
            membership,
            role,
            campus.departments[department_code] if department_code else None,
        )
    return membership


def grant(
    session: Session,
    membership: CollegeMembership,
    role: Role,
    department: Department | None = None,
) -> RoleGrant:
    row = RoleGrant(
        college_id=membership.college_id,
        membership_id=membership.id,
        role=role,
        department_id=department.id if department else None,
    )
    session.add(row)
    session.flush()
    return row


def roster_entry(
    session: Session,
    campus: Campus,
    roll_number: str,
    *,
    department: str = "CSE",
    email: str | None = None,
) -> RosterEntry:
    row = RosterEntry(
        college_id=campus.id,
        department_id=campus.departments[department].id,
        roll_number=roll_number,
        full_name="Roster Name",
        email=email,
        program="B.Tech",
        admission_year=2024,
    )
    session.add(row)
    session.flush()
    return row
