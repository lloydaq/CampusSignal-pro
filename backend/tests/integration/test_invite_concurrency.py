"""Accepting one invite from several browsers at once creates exactly one membership.

Like test_auth_concurrency, this uses independent connections and committed rows on the
disposable test database (a shared rolled-back transaction can't show a race), and removes
what it committed.
"""

import threading
import uuid
from collections import Counter
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import BadRequest, Conflict
from app.core.security import hash_password
from app.models import College, CollegeMembership, MembershipKind, RoleGrant
from app.models.user import User
from app.services.invites import accept_invite, create_invite

pytestmark = pytest.mark.integration

WORKERS = 6


@pytest.fixture
def factory(config: Config, test_database_url: str) -> Iterator[sessionmaker[Session]]:
    command.upgrade(config, "head")
    engine: Engine = create_engine(test_database_url, pool_size=WORKERS, hide_parameters=True)
    started = datetime.now(UTC)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL campussignal.audit_purge = 'on'"))
            conn.execute(text("DELETE FROM audit_log WHERE created_at >= :t"), {"t": started})
            race = "college_id IN (SELECT id FROM colleges WHERE slug LIKE 'race-%')"
            for table in ("role_grants", "college_memberships", "invites"):
                conn.execute(text(f"DELETE FROM {table} WHERE {race}"))  # noqa: S608 - constants
            conn.execute(text("DELETE FROM colleges WHERE slug LIKE 'race-%'"))
            conn.execute(text("DELETE FROM users WHERE email LIKE 'race-%@northfield.example'"))
            conn.execute(text("DELETE FROM rate_limit_counters WHERE bucket_key LIKE 'invite:%'"))
        engine.dispose()


@pytest.mark.parametrize("round_", range(3))
def test_one_invite_accepted_concurrently_makes_one_membership(
    factory: sessionmaker[Session], round_: int
) -> None:
    tag = uuid.uuid4().hex[:10]
    now = datetime.now(UTC)
    with factory() as db:
        college = College(name="Race College", slug=f"race-{tag}", timezone="UTC")
        user = User(
            email=f"race-{tag}@northfield.example",
            password_hash=hash_password("tidal-quartz-lantern"),
            display_name="Race",
        )
        db.add_all([college, user])
        db.flush()
        _, token = create_invite(
            db,
            college=college,
            email=user.email,
            kind=MembershipKind.FACULTY,
            grants=[{"role": "COLLEGE_ADMIN"}],
            invited_by=user,
            now=now,
        )
        db.commit()

    barrier = threading.Barrier(WORKERS)

    def accept(index: int) -> str:
        barrier.wait(timeout=30)
        with factory() as db:
            me = db.execute(select(User).where(User.id == user.id)).scalar_one()
            try:
                accept_invite(
                    db,
                    user=me,
                    token=token,
                    session_token=None,
                    ip_key=f"ip-{index}-{tag}",
                    now=datetime.now(UTC),
                )
            except (BadRequest, Conflict) as exc:
                return exc.error_code
            return "ok"

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        outcomes = Counter(pool.map(accept, range(WORKERS)))
    assert outcomes == {"ok": 1, "token_used": WORKERS - 1}
    with factory() as db:
        memberships = (
            db.execute(select(CollegeMembership).where(CollegeMembership.college_id == college.id))
            .scalars()
            .all()
        )
        grants = (
            db.execute(select(RoleGrant).where(RoleGrant.college_id == college.id)).scalars().all()
        )
    assert len(memberships) == 1
    assert len(grants) == 1
