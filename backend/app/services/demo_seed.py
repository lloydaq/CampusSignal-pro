"""Demo data for development and demos (PRD §21 item 15, architecture.md §5 `seed-demo`).

Three colleges: the fictional "Northfield Institute" and "Riverside College", and
"Mangalore Institute of Technology and Engineering" (MITE) with made-up people. All are
flagged `is_demo` so every screen labels them. Each gets departments, a college admin, a faculty
department admin and a student roster; Northfield also gets an issue coordinator. The
students are NOT accounts: a demo student registers with a roster email and joins by roll
number, which is the Phase 3 exit demo.

All demo accounts share one password that the operator types at the prompt; nothing is
hardcoded. Running it again adds only what is missing. Addresses are fictional
(`.example`), documented here instead of printed:

| College | Account | Role |
|---|---|---|
| Northfield | `priya.menon@northfield.example` | college admin (staff) |
| Northfield | `ravi.sharma@northfield.example` | faculty, department admin of CSE |
| Northfield | `meera.iyer@northfield.example` | staff, issue coordinator |
| Riverside | `meena.joshi@riverside.example` | college admin (staff) |
| Riverside | `arjun.bose@riverside.example` | faculty, department admin of CIVIL |
| MITE | `shreya.kamath@mite.example` | college admin (staff) |
| MITE | `prakash.shetty@mite.example` | faculty, department admin of CSE |
| MITE | `rohan.pai@mite.example` | faculty (CSE) |
| MITE | `deepa.bhat@mite.example` | staff, issue coordinator |

Roster emails are `<roll number in lower case>@<college>.example`; roll numbers are listed
below. Northfield's first student has no roster email (it exercises the approval queue).

Academics (Phase 7): each college gets a current demo term around the seeding date (unless it
already has terms), a few subjects and sections taught by its demo faculty, and a weekly
timetable. Students aren't accounts, so nobody is enrolled: once a demo student joins, an admin
enrolls them by roll number (Manage → Academics). No attendance or scores are invented.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.core.security import hash_password, password_problem
from app.models import (
    AcademicTerm,
    ClassSection,
    College,
    CollegeMembership,
    CollegeStatus,
    Department,
    MembershipKind,
    MembershipStatus,
    Role,
    RoleGrant,
    RosterEntry,
    SectionInstructor,
    Subject,
    TimetableEntry,
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
            DemoAccount(
                "meera.iyer@northfield.example",
                "Meera Iyer",
                MembershipKind.STAFF,
                None,
                (Role.ISSUE_COORDINATOR,),
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
    DemoCollege(
        name="Mangalore Institute of Technology and Engineering",
        slug="mite",
        departments=(
            ("CSE", "Computer Science and Engineering"),
            ("ECE", "Electronics and Communication Engineering"),
            ("MECH", "Mechanical Engineering"),
            ("CIVIL", "Civil Engineering"),
        ),
        accounts=(
            DemoAccount(
                "shreya.kamath@mite.example",
                "Shreya Kamath",
                MembershipKind.STAFF,
                None,
                (Role.COLLEGE_ADMIN,),
            ),
            DemoAccount(
                "prakash.shetty@mite.example",
                "Prakash Shetty",
                MembershipKind.FACULTY,
                "CSE",
                (Role.DEPARTMENT_ADMIN,),
            ),
            DemoAccount(
                "rohan.pai@mite.example",
                "Rohan Pai",
                MembershipKind.FACULTY,
                "CSE",
                (),
            ),
            DemoAccount(
                "deepa.bhat@mite.example",
                "Deepa Bhat",
                MembershipKind.STAFF,
                None,
                (Role.ISSUE_COORDINATOR,),
            ),
        ),
        students=(
            DemoStudent("MITE-CSE-001", "Ananya Hegde", "CSE", 2025),
            DemoStudent("MITE-CSE-002", "Karthik Poojary", "CSE", 2025),
            DemoStudent("MITE-CSE-003", "Fathima Shaikh", "CSE", 2024),
            DemoStudent("MITE-CSE-004", "Joel Pinto", "CSE", 2024),
            DemoStudent("MITE-ECE-001", "Vivek Kini", "ECE", 2025),
            DemoStudent("MITE-ECE-002", "Nisha D'Souza", "ECE", 2024),
            DemoStudent("MITE-ME-001", "Rahul Salian", "MECH", 2025),
            DemoStudent("MITE-CV-001", "Sneha Acharya", "CIVIL", 2025),
        ),
    ),
)


@dataclass(frozen=True)
class DemoSection:
    """A subject and its section "A", taught by `faculty` (an account email, or None)."""

    code: str
    name: str
    department: str
    faculty: str | None
    classes: tuple[tuple[int, str, str, str], ...]  # weekday, starts, ends, room


DEMO_ACADEMICS: dict[str, tuple[DemoSection, ...]] = {
    "northfield": (
        DemoSection(
            "CS301",
            "Compilers",
            "CSE",
            "ravi.sharma@northfield.example",
            (
                (1, "09:00", "10:00", "C-103"),
                (3, "09:00", "10:00", "C-103"),
                (5, "11:00", "12:00", "C-103"),
            ),
        ),
        DemoSection(
            "CS205",
            "Data Structures",
            "CSE",
            "ravi.sharma@northfield.example",
            ((2, "10:00", "11:00", "C-104"), (4, "14:00", "16:00", "Computing lab 2")),
        ),
        DemoSection("ME201", "Thermodynamics", "MECH", None, ((1, "11:00", "12:00", "M-201"),)),
    ),
    "riverside": (
        DemoSection(
            "CV201",
            "Surveying",
            "CIVIL",
            "arjun.bose@riverside.example",
            ((2, "09:00", "10:00", "Field lab"), (4, "09:00", "10:00", "R-12")),
        ),
    ),
    "mite": (
        DemoSection(
            "CS301",
            "Operating Systems",
            "CSE",
            "rohan.pai@mite.example",
            ((1, "10:00", "11:00", "LH-3"), (3, "10:00", "11:00", "LH-3")),
        ),
        DemoSection(
            "CS302",
            "Database Management Systems",
            "CSE",
            "prakash.shetty@mite.example",
            ((2, "11:00", "12:00", "LH-4"), (5, "14:00", "16:00", "DB lab")),
        ),
    ),
}


@dataclass
class SeedReport:
    colleges: int = 0
    departments: int = 0
    accounts: int = 0
    roster_entries: int = 0
    terms: int = 0
    sections: int = 0


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

        _seed_academics(db, demo, college, departments, now, report)

    record_audit(
        db,
        action=ACTION_DEMO_SEEDED,
        metadata={
            "colleges": report.colleges,
            "departments": report.departments,
            "accounts": report.accounts,
            "roster_entries": report.roster_entries,
            "terms": report.terms,
            "sections": report.sections,
        },
    )
    db.commit()
    return report


def _seed_academics(
    db: Session,
    demo: DemoCollege,
    college: College,
    departments: dict[str, Department],
    now: datetime,
    report: SeedReport,
) -> None:
    """A current term around today (only for a college with no terms yet), then the demo
    subjects, their section A, its faculty and timetable, skipping what exists."""
    sections = DEMO_ACADEMICS.get(demo.slug, ())
    if not sections:
        return
    term = db.execute(
        select(AcademicTerm).where(AcademicTerm.college_id == college.id, AcademicTerm.is_current)
    ).scalar_one_or_none()
    if term is None:
        if db.execute(
            select(AcademicTerm.id).where(AcademicTerm.college_id == college.id).limit(1)
        ).first():
            return  # the college has its own terms but none current: leave them alone
        today = now.astimezone(ZoneInfo(college.timezone)).date()
        term = AcademicTerm(
            college_id=college.id,
            name=f"Demo term {today.year}",
            starts_on=today - timedelta(days=60),
            ends_on=today + timedelta(days=90),
            is_current=True,
            created_at=now,
            updated_at=now,
        )
        db.add(term)
        db.flush()
        report.terms += 1
    faculty = {
        email: membership_id
        for email, membership_id in db.execute(
            select(User.email, CollegeMembership.id)
            .join(CollegeMembership, CollegeMembership.user_id == User.id)
            .where(
                CollegeMembership.college_id == college.id,
                CollegeMembership.kind == MembershipKind.FACULTY,
                CollegeMembership.status == MembershipStatus.ACTIVE,
            )
        ).all()
    }
    for demo_section in sections:
        subject = db.execute(
            select(Subject).where(
                Subject.college_id == college.id, Subject.code == demo_section.code
            )
        ).scalar_one_or_none()
        if subject is None:
            subject = Subject(
                college_id=college.id,
                department_id=departments[demo_section.department].id,
                code=demo_section.code,
                name=demo_section.name,
                created_at=now,
                updated_at=now,
            )
            db.add(subject)
            db.flush()
        if db.execute(
            select(ClassSection.id).where(
                ClassSection.college_id == college.id,
                ClassSection.term_id == term.id,
                ClassSection.subject_id == subject.id,
                ClassSection.name == "A",
            )
        ).first():
            continue
        section = ClassSection(
            college_id=college.id,
            term_id=term.id,
            subject_id=subject.id,
            name="A",
            created_at=now,
            updated_at=now,
        )
        db.add(section)
        db.flush()
        report.sections += 1
        teacher = faculty.get(demo_section.faculty) if demo_section.faculty else None
        if teacher is not None:
            db.add(
                SectionInstructor(
                    college_id=college.id, section_id=section.id, membership_id=teacher
                )
            )
        for weekday, starts, ends, room in demo_section.classes:
            db.add(
                TimetableEntry(
                    college_id=college.id,
                    section_id=section.id,
                    weekday=weekday,
                    starts_at=time.fromisoformat(starts),
                    ends_at=time.fromisoformat(ends),
                    room=room,
                )
            )
    db.flush()
