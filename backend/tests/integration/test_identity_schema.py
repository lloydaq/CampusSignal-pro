"""Migration 0003 on a disposable Postgres 17: constraints, append-only audit log, rate limits.

Each test runs inside one transaction that is rolled back, so tests don't affect each
other. Expected database errors happen inside savepoints so the outer transaction stays
usable.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.ratelimit import Limit, current, hit
from app.core.security import hash_password, new_token
from app.models import AuditLog, AuthSession, User, UserToken
from app.services.audit import record_audit

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 21, 10, 7, tzinfo=UTC)


@pytest.fixture
def conn(config: Config, engine: Engine) -> Iterator[Connection]:
    command.upgrade(config, "head")
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture
def session(conn: Connection) -> Iterator[Session]:
    with Session(bind=conn, join_transaction_mode="create_savepoint") as s:
        yield s


def _user(session: Session, email: str = "aarav@northfield.example") -> User:
    user = User(
        email=email, password_hash=hash_password("tidal-quartz-lantern"), display_name="Aarav"
    )
    session.add(user)
    session.flush()
    return user


def test_email_is_unique_case_insensitively(session: Session) -> None:
    _user(session, "Aarav@Northfield.example")
    with pytest.raises(IntegrityError), session.begin_nested():
        _user(session, "aarav@northfield.EXAMPLE")


def test_found_by_email_in_any_case(session: Session) -> None:
    user = _user(session, "Meera@Riverside.example")
    found = session.query(User).filter(User.email == "meera@riverside.example").one()
    assert found.id == user.id
    assert found.status == "ACTIVE"
    assert found.email_verified_at is None


@pytest.mark.parametrize(
    ("column", "value"),
    [("status", "BANNED"), ("platform_role", "SUPERUSER"), ("display_name", "")],
)
def test_check_constraints(session: Session, column: str, value: str) -> None:
    user = _user(session)
    with pytest.raises(IntegrityError), session.begin_nested():
        setattr(user, column, value)
        session.flush()


def test_sessions_and_tokens_store_32_byte_digests_and_cascade(session: Session) -> None:
    user = _user(session)
    session.add(
        AuthSession(
            id_hash=new_token()[1],
            user_id=user.id,
            csrf_secret=new_token()[1],
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    session.add(
        UserToken(
            user_id=user.id,
            purpose="VERIFY_EMAIL",
            token_hash=new_token()[1],
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )
    session.flush()
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(
            AuthSession(
                id_hash=b"short",
                user_id=user.id,
                csrf_secret=new_token()[1],
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        session.flush()

    session.delete(user)
    session.flush()
    assert session.query(AuthSession).count() == 0
    assert session.query(UserToken).count() == 0


def test_audit_log_is_append_only(session: Session, conn: Connection) -> None:
    entry = record_audit(session, action="test.event", metadata={"via": "test"})
    session.flush()
    for statement in (
        "UPDATE audit_log SET action = 'tampered'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ):
        with pytest.raises(DBAPIError, match="append-only"), conn.begin_nested():
            conn.execute(text(statement))
    assert session.get(AuditLog, entry.id) is not None


def test_audit_purge_flag_allows_delete_only(session: Session, conn: Connection) -> None:
    record_audit(session, action="test.old")
    session.flush()
    with conn.begin_nested():
        conn.execute(text("SET LOCAL campussignal.audit_purge = 'on'"))
        with pytest.raises(DBAPIError, match="append-only"), conn.begin_nested():
            conn.execute(text("UPDATE audit_log SET action = 'tampered'"))
        deleted = conn.execute(text("DELETE FROM audit_log WHERE action = 'test.old'")).rowcount
    assert deleted == 1


def test_audit_entry_round_trip(session: Session) -> None:
    actor = _user(session)
    entry = record_audit(
        session,
        action="auth.platform_admin_created",
        actor_user_id=actor.id,
        target_type="user",
        target_id=str(actor.id),
        metadata={"via": "cli"},
    )
    session.flush()
    session.refresh(entry)
    assert entry.created_at is not None
    assert entry.data == {"via": "cli"}
    assert isinstance(entry.id, uuid.UUID)


def test_rate_limit_counts_per_key_and_window(session: Session) -> None:
    limit = Limit(name="test", max_hits=3, window=timedelta(minutes=15))
    for expected in (1, 2, 3):
        assert hit(session, limit, "k1", NOW).count == expected
    assert current(session, limit, "k1", NOW).exceeded
    assert current(session, limit, "k2", NOW).count == 0
    later = NOW + timedelta(minutes=15)
    assert current(session, limit, "k1", later).count == 0
    assert hit(session, limit, "k1", later).count == 1
