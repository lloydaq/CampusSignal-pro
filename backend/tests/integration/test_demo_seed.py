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


def test_adds_two_labelled_demo_colleges_without_printing_accounts(
    factory: sessionmaker[Session], session: Session, clock: Clock
) -> None:
    code, output = _seed(factory, clock)

    assert code == cli.EXIT_OK
    assert "Added 2 colleges, 4 departments, 4 accounts and 8 roster entries." in output
    assert PRIYA not in output and PASSWORD not in output
    colleges = session.execute(select(College).order_by(College.slug)).scalars().all()
    assert [(c.name, c.is_demo, c.status) for c in colleges] == [
        ("Northfield Institute", True, "ACTIVE"),
        ("Riverside College", True, "ACTIVE"),
    ]
    entry = session.execute(
        select(AuditLog).where(AuditLog.action == demo_seed.ACTION_DEMO_SEEDED)
    ).scalar_one()
    assert entry.data["colleges"] == 2


def test_running_it_again_adds_nothing(
    factory: sessionmaker[Session], session: Session, clock: Clock
) -> None:
    _seed(factory, clock)
    code, output = _seed(factory, clock)

    assert code == cli.EXIT_OK
    assert "Added 0 colleges, 0 departments, 0 accounts and 0 roster entries." in output
    assert session.execute(select(func.count()).select_from(College)).scalar_one() == 2
    assert session.execute(select(func.count()).select_from(CollegeMembership)).scalar_one() == 4


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
    assert session.execute(select(func.count()).select_from(RosterEntry)).scalar_one() == 8
