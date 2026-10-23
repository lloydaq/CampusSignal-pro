"""`create-platform-admin` against a disposable Postgres (ADMIN-005, P-7, ADR-13)."""

import io
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, select
from sqlalchemy.orm import Session, sessionmaker

from app.cli import main as cli
from app.core.mailer import InMemoryMailer
from app.core.security import verify_password
from app.models import AuditLog, PlatformRole, User
from app.services.platform_admins import ACTION_PLATFORM_ADMIN_CREATED
from tests.integration.auth_helpers import EMAIL, create_user, login
from tests.integration.conftest import Clock

pytestmark = pytest.mark.integration

ADMIN_EMAIL = "ops@campussignal.example"
ADMIN_PASSWORD = "harbour-violet-compass"


@pytest.fixture
def factory(conn: Connection) -> sessionmaker[Session]:
    return sessionmaker(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)


def _create(
    factory: Callable[[], Session], clock: Clock, email: str = ADMIN_EMAIL
) -> tuple[int, str]:
    out = io.StringIO()
    code = cli.main(
        ["create-platform-admin", "--email", email, "--display-name", "  Platform   Ops "],
        session_factory=factory,
        read_password=lambda prompt: ADMIN_PASSWORD,
        now=clock.now,
        out=out,
    )
    return code, out.getvalue()


def test_creates_a_verified_platform_admin_and_audits_it(
    factory: sessionmaker[Session], session: Session, clock: Clock
) -> None:
    code, output = _create(factory, clock, email=" Ops@CampusSignal.example ")

    assert code == cli.EXIT_OK
    user = session.execute(select(User).where(User.email == ADMIN_EMAIL)).scalar_one()
    assert user.platform_role == PlatformRole.PLATFORM_ADMIN
    assert user.email_verified_at == clock.now
    assert user.display_name == "Platform Ops"
    assert verify_password(user.password_hash, ADMIN_PASSWORD)
    assert output == f"Created platform admin {user.id}.\n"
    assert ADMIN_EMAIL not in output.lower() and ADMIN_PASSWORD not in output

    entry = session.execute(
        select(AuditLog).where(AuditLog.action == ACTION_PLATFORM_ADMIN_CREATED)
    ).scalar_one()
    assert (entry.target_type, entry.target_id) == ("user", str(user.id))
    assert entry.actor_user_id is None
    assert entry.data == {"via": "cli"}


def test_existing_email_is_refused_not_promoted(
    factory: sessionmaker[Session],
    session: Session,
    clock: Clock,
    api: TestClient,
    mailer: InMemoryMailer,
) -> None:
    create_user(api, mailer)  # an ordinary, verified account

    code, output = _create(factory, clock, email=EMAIL.upper())

    assert code == cli.EXIT_FAILED
    assert "already exists" in output and "Nothing was created" in output
    users = session.execute(select(User)).scalars().all()
    assert [u.platform_role for u in users] == [None]
    assert (
        session.execute(
            select(AuditLog).where(AuditLog.action == ACTION_PLATFORM_ADMIN_CREATED)
        ).first()
        is None
    )


def test_running_twice_creates_one_account(
    factory: sessionmaker[Session], session: Session, clock: Clock
) -> None:
    assert _create(factory, clock)[0] == cli.EXIT_OK
    assert _create(factory, clock)[0] == cli.EXIT_FAILED
    assert len(session.execute(select(User)).scalars().all()) == 1


def test_the_new_admin_can_sign_in_with_privileged_limits(
    factory: sessionmaker[Session], clock: Clock, api: TestClient
) -> None:
    assert _create(factory, clock)[0] == cli.EXIT_OK

    response = login(api, ADMIN_EMAIL, ADMIN_PASSWORD)

    assert response.status_code == 200
    assert "max-age=604800" in response.headers["set-cookie"].lower()  # 7 days (P-10)
