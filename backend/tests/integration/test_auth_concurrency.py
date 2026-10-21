"""Rate limits under real concurrency (security review B1).

The rest of the integration suite shares one rolled-back transaction, which cannot show a
race. These tests use independent connections and committed data on the disposable local
test database, start the requests together, and clean up what they committed.
"""

import threading
import uuid
from collections import Counter
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core import ratelimit
from app.core.errors import BadRequest, InvalidCredentials, RateLimited
from app.core.security import hash_password
from app.models.user import User
from app.services import auth as auth_service
from tests.conftest import make_settings

pytestmark = pytest.mark.integration

PASSWORD = "tidal-quartz-lantern"
WRONG = "not-the-right-password"
WORKERS = 10  # each Argon2 check holds 64 MiB, so keep the parallelism modest


@pytest.fixture
def committed(
    config: Config, test_database_url: str
) -> Iterator[tuple[Engine, sessionmaker[Session], datetime]]:
    """Independent connections on the verified-disposable database, with cleanup."""
    command.upgrade(config, "head")  # a fresh database (CI) has no tables until migrated
    engine = create_engine(test_database_url, pool_size=WORKERS, hide_parameters=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    started = datetime.now(UTC)
    try:
        yield engine, factory, started
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE email LIKE 'race-%@northfield.example'"))
            conn.execute(text("DELETE FROM rate_limit_counters WHERE bucket_key LIKE '%:%'"))
            conn.execute(text("SET LOCAL campussignal.audit_purge = 'on'"))
            conn.execute(text("DELETE FROM audit_log WHERE created_at >= :t"), {"t": started})
        engine.dispose()


def _user(factory: sessionmaker[Session]) -> User:
    with factory() as db:
        user = User(
            email=f"race-{uuid.uuid4().hex[:12]}@northfield.example",
            password_hash=hash_password(PASSWORD),
            display_name="Race Test",
        )
        db.add(user)
        db.commit()
        return user


def _run_together(
    factory: sessionmaker[Session], attempts: int, attempt: Callable[[Session, int], Any]
) -> Counter[str]:
    """Run `attempt` `attempts` times on separate connections, released at the same instant
    (the first WORKERS), and count outcomes by exception type (or 'ok')."""
    barrier = threading.Barrier(min(attempts, WORKERS))

    def run(index: int) -> str:
        if index < WORKERS:
            barrier.wait(timeout=30)
        with factory() as db:
            try:
                attempt(db, index)
            except (InvalidCredentials, RateLimited, BadRequest) as exc:
                return type(exc).__name__
            return "ok"

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return Counter(pool.map(run, range(attempts)))


def _login(db: Session, email: str, ip: str, password: str = WRONG) -> None:
    auth_service.login(
        db,
        make_settings(),
        email=email,
        password=password,
        ip_key=ip,
        old_session_token=None,
        now=datetime.now(UTC),
    )


@pytest.mark.parametrize("round_", range(3))  # repeated to shake out timing luck
def test_parallel_wrong_passwords_for_one_email_are_capped_at_five(
    committed: Any, round_: int
) -> None:
    _, factory, _ = committed
    user = _user(factory)
    outcomes = _run_together(
        factory, WORKERS, lambda db, i: _login(db, user.email, f"ip-{uuid.uuid4().hex}")
    )
    assert outcomes == {"InvalidCredentials": 5, "RateLimited": WORKERS - 5}


def test_parallel_guesses_at_a_non_existent_email_are_capped_too(committed: Any) -> None:
    _, factory, _ = committed
    email = f"race-{uuid.uuid4().hex[:12]}@northfield.example"
    outcomes = _run_together(factory, WORKERS, lambda db, i: _login(db, email, f"ip-{i}"))
    assert outcomes == {"InvalidCredentials": 5, "RateLimited": WORKERS - 5}


def test_parallel_guesses_from_one_address_are_capped_at_twenty(committed: Any) -> None:
    _, factory, _ = committed
    ip = f"ip-{uuid.uuid4().hex}"
    outcomes = _run_together(
        factory,
        30,
        lambda db, i: _login(db, f"race-{uuid.uuid4().hex[:12]}@northfield.example", ip),
    )
    assert outcomes == {"InvalidCredentials": 20, "RateLimited": 10}


def test_the_correct_password_never_gets_past_a_used_up_limit(committed: Any) -> None:
    _, factory, _ = committed
    user = _user(factory)
    ip = f"ip-{uuid.uuid4().hex}"
    _run_together(factory, WORKERS, lambda db, i: _login(db, user.email, ip))
    with factory() as db, pytest.raises(RateLimited):
        _login(db, user.email, ip, PASSWORD)


def test_a_success_clears_the_email_counter_and_refunds_the_address(committed: Any) -> None:
    _, factory, _ = committed
    user = _user(factory)
    ip = f"ip-{uuid.uuid4().hex}"
    for _ in range(4):
        with factory() as db, pytest.raises(InvalidCredentials):
            _login(db, user.email, ip)
    with factory() as db:
        _login(db, user.email, ip, PASSWORD)  # succeeds
    now = datetime.now(UTC)
    with factory() as db:
        email_key = ratelimit.hashed_key(user.email)
        assert ratelimit.current(db, auth_service.LOGIN_EMAIL, email_key, now).count == 0
        assert ratelimit.current(db, auth_service.LOGIN_IP, ip, now).count == 4  # failures only


def test_an_address_that_is_locked_out_does_not_use_up_the_email(committed: Any) -> None:
    _, factory, _ = committed
    ip = f"ip-{uuid.uuid4().hex}"
    for _ in range(20):  # fill the address's allowance with other emails
        with factory() as db, pytest.raises(InvalidCredentials):
            _login(db, f"race-{uuid.uuid4().hex[:12]}@northfield.example", ip)
    user = _user(factory)
    for _ in range(10):
        with factory() as db, pytest.raises(RateLimited):
            _login(db, user.email, ip)
    with factory() as db:
        count = ratelimit.current(
            db, auth_service.LOGIN_EMAIL, ratelimit.hashed_key(user.email), datetime.now(UTC)
        ).count
    assert count == 0  # the person's own sign-ins from elsewhere are unaffected


def test_the_lockout_is_audited_exactly_once_under_concurrency(committed: Any) -> None:
    engine, factory, started = committed
    user = _user(factory)
    _run_together(factory, WORKERS, lambda db, i: _login(db, user.email, f"ip-{uuid.uuid4().hex}"))
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT count(*) FROM audit_log WHERE action = 'auth.login_rate_limited' "
                "AND created_at >= :t AND target_id = :u"
            ),
            {"t": started, "u": str(user.id)},
        ).scalar()
    assert rows == 1


@pytest.mark.parametrize("round_", range(3))
def test_parallel_wrong_current_passwords_are_capped_at_five(committed: Any, round_: int) -> None:
    _, factory, _ = committed
    user = _user(factory)

    def attempt(db: Session, _: int) -> None:
        loaded = db.get(User, user.id)
        assert loaded is not None
        auth_service.change_password(
            db,
            make_settings(),
            user=loaded,
            current_password=WRONG,
            new_password="copper-meadow-harbour",
            now=datetime.now(UTC),
        )

    outcomes = _run_together(factory, WORKERS, attempt)
    assert outcomes == {"BadRequest": 5, "RateLimited": WORKERS - 5}
