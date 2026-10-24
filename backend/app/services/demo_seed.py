"""Demo data for development and demos (PRD §21 item 15, architecture.md §5 `seed-demo`).

Two fictional colleges, "Northfield Institute" and "Riverside College", both flagged
`is_demo` so every screen labels them. Each gets departments, a college admin, a faculty
department admin and a student roster. The students are NOT accounts: a demo student
registers with a roster email and joins by roll number, which is the Phase 3 exit demo.

All demo accounts share one password that the operator types at the prompt; nothing is
hardcoded. Running it again adds only what is missing. Addresses are fictional
(`.example`), documented here instead of printed:

| College | Account | Role |
|---|---|---|
| Northfield | `priya.menon@northfield.example` | college admin (staff) |
| Northfield | `ravi.sharma@northfield.example` | faculty, department admin of CSE |
| Riverside | `meena.joshi@riverside.example` | college admin (staff) |
| Riverside | `arjun.bose@riverside.example` | faculty, department admin of CIVIL |

Roster emails are `<roll number in lower case>@<college>.example`; roll numbers are listed
below. Northfield's first student has no roster email (it exercises the approval queue).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.core.security import hash_password, password_problem
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
from app.services.audit import record_audit

ACTION_DEMO_SEEDED = "platform.demo_seeded"


@dataclass(frozen=True)
class DemoAccount:
    email: str
    display_name: str
    kind: MembershipKind
    department: str | None
    roles: tuple[Role, ...]


@dataclass(frozen=True)
class DemoStudent:
    roll_number: str
    full_name: str
    department: str
    admission_year: int
    has_email: bool = True


@dataclass(frozen=True)
class DemoCollege:
    name: str
    slug: str
    departments: tuple[tuple[str, str], ...]
    accounts: tuple[DemoAccount, ...]
    students: tuple[DemoStudent, ...]

    @property
    def domain(self) -> str:
        return f"{self.slug}.example"


DEMO_COLLEGES = (
    DemoCollege(
        name="Northfield Institute",
        slug="northfield",
        departments=(("CSE", "Computer Science"), ("MECH", "Mechanical Engineering")),
        accounts=(
            DemoAccount(
                "priya.menon@northfield.example",
                "Priya Menon",
                MembershipKind.STAFF,
                None,
                (Role.COLLEGE_ADMIN,),
            ),
            DemoAccount(
                "ravi.sharma@northfield.example",
                "Ravi Sharma",
                MembershipKind.FACULTY,
                "CSE",
                (Role.DEPARTMENT_ADMIN,),
            ),
        ),
        students=(
            DemoStudent("NF-CSE-001", "Aarav Nair", "CSE", 2025, has_email=False),
            DemoStudent("NF-CSE-002", "Ishita Verma", "CSE", 2025),
            DemoStudent("NF-CSE-003", "Kabir Shah", "CSE", 2024),
            DemoStudent("NF-ME-001", "Dev Patel", "MECH", 2025),
            DemoStudent("NF-ME-002", "Sana Khan", "MECH", 2024),
        ),
    ),
    DemoCollege(
        name="Riverside College",
        slug="riverside",
        departments=(("CSE", "Computer Science"), ("CIVIL", "Civil Engineering")),
        accounts=(
            DemoAccount(
                "meena.joshi@riverside.example",
                "Meena Joshi",
                MembershipKind.STAFF,
                None,
                (Role.COLLEGE_ADMIN,),
            ),
            DemoAccount(
                "arjun.bose@riverside.example",
                "Arjun Bose",
                MembershipKind.FACULTY,
                "CIVIL",
                (Role.DEPARTMENT_ADMIN,),
            ),
        ),
        students=(
            DemoStudent("RC-CSE-001", "Tara Iyer", "CSE", 2025),
            DemoStudent("RC-CSE-002", "Nikhil Rao", "CSE", 2024),
            DemoStudent("RC-CIV-001", "Zoya Ansari", "CIVIL", 2025),
        ),
    ),
)


@dataclass
class SeedReport:
    colleges: int = 0
    departments: int = 0
    accounts: int = 0
    roster_entries: int = 0


def _email(college: DemoCollege, student: DemoStudent) -> str | None:
    return f"{student.roll_number.lower()}@{college.domain}" if student.has_email else None


def seed_demo(db: Session, *, password: str, now: datetime) -> SeedReport:
    """Add the demo colleges and what belongs to them; skip what already exists."""
    for demo in DEMO_COLLEGES:
        for account in demo.accounts:
            problem = password_problem(password, email=account.email)
            if problem is not None:
                raise ValidationFailed.field("password", problem)
    report = SeedReport()
    password_hash = hash_password(password)
    for demo in DEMO_COLLEGES:
        college = db.execute(select(College).where(College.slug == demo.slug)).scalar_one_or_none()
        if college is None:
            college = College(
                name=demo.name,
                slug=demo.slug,
                timezone="Asia/Kolkata",
                status=CollegeStatus.ACTIVE,
                email_domains=[demo.domain],
                is_demo=True,
                created_at=now,
                updated_at=now,
            )
            db.add(college)
            db.flush()
            report.colleges += 1

        departments: dict[str, Department] = {
            d.code: d
            for d in db.execute(select(Department).where(Department.college_id == college.id))
            .scalars()
            .all()
        }
        for code, name in demo.departments:
            if code not in departments:
                departments[code] = Department(
                    college_id=college.id, code=code, name=name, created_at=now, updated_at=now
                )
                db.add(departments[code])
                report.departments += 1
        db.flush()

        existing_rolls = set(
            db.execute(
                select(RosterEntry.roll_number).where(RosterEntry.college_id == college.id)
            ).scalars()
        )
        for student in demo.students:
            if student.roll_number in existing_rolls:
                continue
            db.add(
                RosterEntry(
                    college_id=college.id,
                    department_id=departments[student.department].id,
                    roll_number=student.roll_number,
                    full_name=student.full_name,
                    email=_email(demo, student),
                    program="B.Tech",
                    admission_year=student.admission_year,
                    created_at=now,
                )
            )
            report.roster_entries += 1

        for account in demo.accounts:
            if db.execute(select(User).where(User.email == account.email)).scalar_one_or_none():
                continue
            user = User(
                email=account.email,
                password_hash=password_hash,
                display_name=account.display_name,
                email_verified_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(user)
            db.flush()
            department = departments[account.department] if account.department else None
            membership = CollegeMembership(
                user_id=user.id,
                college_id=college.id,
                kind=account.kind,
                status=MembershipStatus.ACTIVE,
                department_id=department.id if department else None,
                created_at=now,
                updated_at=now,
            )
            db.add(membership)
            db.flush()
            for role in account.roles:
                db.add(
                    RoleGrant(
                        college_id=college.id,
                        membership_id=membership.id,
                        role=role,
                        department_id=department.id
                        if role == Role.DEPARTMENT_ADMIN and department
                        else None,
                        created_at=now,
                    )
                )
            report.accounts += 1

    record_audit(
        db,
        action=ACTION_DEMO_SEEDED,
        metadata={
            "colleges": report.colleges,
            "departments": report.departments,
            "accounts": report.accounts,
            "roster_entries": report.roster_entries,
        },
    )
    db.commit()
    return report
