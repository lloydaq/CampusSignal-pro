"""Retention purges and `python -m app.jobs run-due` against a disposable Postgres
(architecture.md §8.3). Each purge removes rows at or past its cutoff and keeps the row
one second short of it; a second run deletes nothing."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Connection, Engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password, new_token
from app.jobs import main as jobs
from app.models import AuditLog, AuthSession, RateLimitCounter, User, UserToken
from app.models.user_token import TokenPurpose
from app.services import retention
from tests.conftest import make_settings

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
SECOND = timedelta(seconds=1)
SETTINGS = make_settings()  # 7-day idle, 30-day absolute session limits
IDLE = timedelta(days=7)
ABSOLUTE = timedelta(days=30)


@pytest.fixture
def factory(conn: Connection) -> sessionmaker[Session]:
    return sessionmaker(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
def user(session: Session) -> User:
    user = User(
        email="aarav@northfield.example",
        password_hash=hash_password("tidal-quartz-lantern"),
        display_name="Aarav",
    )
    session.add(user)
    session.commit()
    return user


def _session_row(
    user: User, name: str, *, created: datetime, seen: datetime, expires: datetime
) -> AuthSession:
    # The name is kept in the CSRF secret so tests can tell rows apart.
    return AuthSession(
        id_hash=new_token()[1],
        user_id=user.id,
        csrf_secret=name.encode().ljust(32, b"."),
        created_at=created,
        last_seen_at=seen,
        expires_at=expires,
    )


def _remaining_sessions(session: Session) -> set[str]:
    rows = session.execute(select(AuthSession.csrf_secret)).scalars()
    return {secret.rstrip(b".").decode() for secret in rows}


def _seed(session: Session, user: User) -> None:
    recent = NOW - timedelta(hours=1)
    session.add_all(
        [
            _session_row(
                user, "live", created=recent, seen=recent, expires=NOW + timedelta(days=29)
            ),
            _session_row(user, "expired", created=NOW - IDLE, seen=recent, expires=NOW),
            _session_row(user, "idle", created=NOW - IDLE, seen=NOW - IDLE, expires=NOW + ABSOLUTE),
            _session_row(
                user,
                "almost-idle",
                created=NOW - IDLE,
                seen=NOW - IDLE + SECOND,
                expires=NOW + ABSOLUTE,
            ),
            _session_row(user, "too-old", created=NOW - ABSOLUTE, seen=recent, expires=NOW + IDLE),
            _session_row(
                user,
                "almost-too-old",
                created=NOW - ABSOLUTE + SECOND,
                seen=recent,
                expires=NOW + IDLE,
            ),
        ]
    )
    for name, expires in (
        ("stale", NOW - retention.TOKEN_GRACE),
        ("in-grace", NOW - retention.TOKEN_GRACE + SECOND),
        ("valid", NOW + timedelta(hours=1)),
    ):
        session.add(
            UserToken(
                user_id=user.id,
                purpose=TokenPurpose.VERIFY_EMAIL,
                token_hash=name.encode().ljust(32, b"."),
                created_at=expires - timedelta(hours=24),
                expires_at=expires,
            )
        )
    for key, start in (
        ("old", NOW - retention.RATE_COUNTER_MAX_AGE),
        ("recent", NOW - retention.RATE_COUNTER_MAX_AGE + SECOND),
    ):
        session.add(RateLimitCounter(bucket_key=key, window_start=start, count=1))
    for action, created in (
        ("test.expired", NOW - retention.AUDIT_RETENTION - SECOND),
        ("test.at_cutoff", NOW - retention.AUDIT_RETENTION),
        ("test.recent", NOW - timedelta(days=1)),
    ):
        session.add(AuditLog(action=action, data={}, created_at=created))
    session.commit()


def test_each_purge_deletes_only_rows_past_its_cutoff(
    factory: sessionmaker[Session], session: Session, user: User
) -> None:
    _seed(session, user)

    outcomes = retention.run_purges(factory, SETTINGS, NOW)

    assert {o.name: o.deleted for o in outcomes} == {
        "sessions": 3,
        "user_tokens": 1,
        "rate_limit_counters": 1,
        "audit_log": 1,
    }
    assert all(o.error_type is None for o in outcomes)
    session.expire_all()
    assert _remaining_sessions(session) == {"live", "almost-idle", "almost-too-old"}
    tokens = session.execute(select(UserToken.token_hash)).scalars()
    assert {t.rstrip(b".").decode() for t in tokens} == {"in-grace", "valid"}
    assert session.execute(select(RateLimitCounter.bucket_key)).scalars().all() == ["recent"]
    actions = session.execute(select(AuditLog.action)).scalars().all()
    assert sorted(actions) == ["test.at_cutoff", "test.recent"]


def test_a_second_run_deletes_nothing(
    factory: sessionmaker[Session], session: Session, user: User
) -> None:
    _seed(session, user)
    retention.run_purges(factory, SETTINGS, NOW)

    again = retention.run_purges(factory, SETTINGS, NOW)

    assert [o.deleted for o in again] == [0, 0, 0, 0]


def test_the_audit_purge_flag_does_not_outlive_its_transaction(
    conn: Connection, engine: Engine
) -> None:
    """Uses its own connection: the shared test transaction never ends, so a transaction-
    local setting would stay on there for the whole test."""
    with engine.connect() as other:
        with other.begin() as transaction:
            retention.purge_audit_log(Session(bind=other), SETTINGS, NOW)
            transaction.rollback()
        with other.begin() as transaction:
            other.execute(
                text("INSERT INTO audit_log (action, metadata) VALUES ('test.row', '{}')")
            )
            with pytest.raises(DBAPIError, match="append-only"):
                other.execute(text("DELETE FROM audit_log"))
            transaction.rollback()


def test_run_due_logs_counts_only(
    factory: sessionmaker[Session],
    session: Session,
    user: User,
    test_database_url: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(session, user)

    code = jobs.main(
        ["run-due"],
        settings=make_settings(database_url=test_database_url),
        session_factory=factory,
        now=NOW,
    )

    assert code == jobs.EXIT_OK
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    purges = {
        line["purge"]: line["deleted"] for line in lines if line["message"] == "retention_purge"
    }
    assert purges == {"sessions": 3, "user_tokens": 1, "rate_limit_counters": 1, "audit_log": 1}
    assert session.execute(select(func.count()).select_from(AuthSession)).scalar() == 3
