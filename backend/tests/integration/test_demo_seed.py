"""`seed-demo` against a disposable Postgres: the data it adds works end to end (PRD §21)."""

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.cli import main as cli
from app.core.mailer import InMemoryMailer
from app.models import AuditLog, College, CollegeMembership, RosterEntry
from app.services import demo_seed
from tests.integration.auth_helpers import PREFIX, create_user, csrf, login
from tests.integration.conftest import Clock

pytestmark = pytest.mark.integration

PASSWORD = "tidal-quartz-lantern"
PRIYA = "priya.menon@northfield.example"
MEENA = "meena.joshi@riverside.example"


def _seed(factory: sessionmaker[Session], clock: Clock) -> tuple[int, str]:
    out = io.StringIO()
    code = cli.main(
        ["seed-demo"],
        session_factory=factory,
        read_password=lambda prompt: PASSWORD,
        now=clock.now,
        out=out,
    )
    return code, out.getvalue()


@pytest.fixture
def factory(session: Session) -> sessionmaker[Session]:
    return sessionmaker(
        bind=session.get_bind(), join_transaction_mode="create_savepoint", expire_on_commit=False
    )


def test_adds_the_labelled_demo_colleges_without_printing_accounts(
    factory: sessionmaker[Session], session: Session, clock: Clock
) -> None:
    code, output = _seed(factory, clock)

    assert code == cli.EXIT_OK
    assert "Added 3 colleges, 8 departments, 9 accounts and 16 roster entries." in output
    assert PRIYA not in output and PASSWORD not in output
    colleges = session.execute(select(College).order_by(College.slug)).scalars().all()
    assert [(c.name, c.is_demo, c.status) for c in colleges] == [
        ("Mangalore Institute of Technology and Engineering", True, "ACTIVE"),
        ("Northfield Institute", True, "ACTIVE"),
        ("Riverside College", True, "ACTIVE"),
    ]
    entry = session.execute(
        select(AuditLog).where(AuditLog.action == demo_seed.ACTION_DEMO_SEEDED)
    ).scalar_one()
    assert entry.data["colleges"] == 3


def test_running_it_again_adds_nothing(
    factory: sessionmaker[Session], session: Session, clock: Clock
) -> None:
    _seed(factory, clock)
    code, output = _seed(factory, clock)

    assert code == cli.EXIT_OK
    assert "Added 0 colleges, 0 departments, 0 accounts and 0 roster entries." in output
    assert session.execute(select(func.count()).select_from(College)).scalar_one() == 3
    assert session.execute(select(func.count()).select_from(CollegeMembership)).scalar_one() == 9


def test_a_weak_password_creates_nothing(
    factory: sessionmaker[Session], session: Session, clock: Clock
) -> None:
    out = io.StringIO()
    code = cli.main(
        ["seed-demo"],
        session_factory=factory,
        read_password=lambda prompt: "password",
        now=clock.now,
        out=out,
    )
    assert code == cli.EXIT_FAILED
    assert session.execute(select(func.count()).select_from(College)).scalar_one() == 0


def test_demo_admins_manage_only_their_own_college(
    factory: sessionmaker[Session], api: TestClient, clock: Clock
) -> None:
    _seed(factory, clock)

    assert login(api, PRIYA, PASSWORD).status_code == 200
    me = api.get(f"{PREFIX}/me").json()
    assert "manage_college" in me["capabilities"]
    northfield = api.get(f"{PREFIX}/campus/roster").json()["items"]
    assert sorted(e["roll_number"] for e in northfield) == [
        "NF-CSE-001",
        "NF-CSE-002",
        "NF-CSE-003",
        "NF-ME-001",
        "NF-ME-002",
    ]

    api.cookies.clear()
    assert login(api, MEENA, PASSWORD).status_code == 200
    riverside = api.get(f"{PREFIX}/campus/roster").json()["items"]
    assert all(e["roll_number"].startswith("RC-") for e in riverside)


def test_the_exit_demo_student_joins_by_roster_email(
    factory: sessionmaker[Session], api: TestClient, mailer: InMemoryMailer, clock: Clock
) -> None:
    """A student registers with their roster email and is in; one without an email waits."""
    _seed(factory, clock)

    create_user(api, mailer, email="nf-cse-002@northfield.example", password=PASSWORD)
    assert login(api, "nf-cse-002@northfield.example", PASSWORD).status_code == 200
    joined = api.post(
        f"{PREFIX}/me/membership-requests",
        json={"college_slug": "northfield", "roll_number": "nf-cse-002"},
        headers=csrf(api),
    )
    assert (joined.status_code, joined.json()["status"]) == (201, "ACTIVE")

    api.cookies.clear()
    create_user(api, mailer, email="aarav.nair@mail.example", password=PASSWORD)
    assert login(api, "aarav.nair@mail.example", PASSWORD).status_code == 200
    waiting = api.post(
        f"{PREFIX}/me/membership-requests",
        json={"college_slug": "northfield", "roll_number": "NF-CSE-001"},
        headers=csrf(api),
    )
    assert (waiting.status_code, waiting.json()["status"]) == (202, "PENDING")


def test_no_roster_entry_is_claimed_by_seeding(
    factory: sessionmaker[Session], session: Session, clock: Clock
) -> None:
    _seed(factory, clock)
    claimed = session.execute(
        select(func.count())
        .select_from(CollegeMembership)
        .where(CollegeMembership.roster_entry_id.is_not(None))
    ).scalar_one()
    assert claimed == 0
    assert session.execute(select(func.count()).select_from(RosterEntry)).scalar_one() == 16


RAVI = "ravi.sharma@northfield.example"


def test_demo_academics_are_set_up_once_and_taught_by_demo_faculty(
    factory: sessionmaker[Session], api: TestClient, mailer: InMemoryMailer, clock: Clock
) -> None:
    """A current term, sections with faculty and a timetable; nobody enrolled, nothing scored."""
    _, output = _seed(factory, clock)
    assert "Academic setup: 3 terms and 6 sections." in output
    _, again = _seed(factory, clock)
    assert "Academic setup: 0 terms and 0 sections." in again

    assert login(api, RAVI, PASSWORD).status_code == 200
    teaching = api.get(f"{PREFIX}/campus/teaching/sections").json()
    assert teaching["term"]["name"] == "Demo term 2026" and teaching["term"]["is_current"]
    assert sorted((s["subject"]["code"], s["enrollment_count"]) for s in teaching["items"]) == [
        ("CS205", 0),
        ("CS301", 0),
    ]
    cs301 = next(s for s in teaching["items"] if s["subject"]["code"] == "CS301")
    timetable = api.get(f"{PREFIX}/campus/sections/{cs301['id']}/timetable").json()["items"]
    assert [(e["weekday"], e["starts_at"], e["room"]) for e in timetable] == [
        (1, "09:00:00", "C-103"),
        (3, "09:00:00", "C-103"),
        (5, "11:00:00", "C-103"),
    ]

    # A demo student who joins can be enrolled by roll number and then sees the timetable.
    api.cookies.clear()
    create_user(api, mailer, email="nf-cse-002@northfield.example", password=PASSWORD)
    assert login(api, "nf-cse-002@northfield.example", PASSWORD).status_code == 200
    api.post(
        f"{PREFIX}/me/membership-requests",
        json={"college_slug": "northfield", "roll_number": "NF-CSE-002"},
        headers=csrf(api),
    )
    api.cookies.clear()
    assert login(api, RAVI, PASSWORD).status_code == 200  # department admin of CSE
    enrolled = api.post(
        f"{PREFIX}/campus/sections/{cs301['id']}/enrollments/import",
        json={"csv": "roll_number\nNF-CSE-002\n"},
        headers=csrf(api),
    )
    assert enrolled.status_code == 201, enrolled.text
    api.cookies.clear()
    assert login(api, "nf-cse-002@northfield.example", PASSWORD).status_code == 200
    week = api.get(f"{PREFIX}/campus/me/timetable").json()
    assert week["is_demo"] and len(week["classes"]) == 3
