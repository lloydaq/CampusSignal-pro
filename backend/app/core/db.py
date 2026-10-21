"""Database engine, sessions, model base and readiness check (architecture.md §8, §16).

Development uses a hosted Supabase Postgres through its session pooler; CI uses a
disposable Postgres 17 service. The backend talks plain PostgreSQL either way.
"""

import logging
from collections.abc import Iterator
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import Request
from sqlalchemy import Engine, MetaData, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings

logger = logging.getLogger("app.db")

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

# Deterministic constraint names so Alembic migrations are reviewable and reversible.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Small pool: the Supabase free plan has limited pooler connections. Connections are
# recycled before the pooler drops idle ones and checked before use.
POOL_SIZE = 5
MAX_OVERFLOW = 5
POOL_RECYCLE_SECONDS = 300
CONNECT_TIMEOUT_SECONDS = 5
READINESS_STATEMENT_TIMEOUT_MS = 3000


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_db_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_recycle=POOL_RECYCLE_SECONDS,
        pool_pre_ping=True,
        # Keep bound parameters (emails, hashes, academic values) out of exception
        # messages, which the middleware logs with tracebacks.
        hide_parameters=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


@lru_cache
def expected_migration_heads() -> frozenset[str]:
    return frozenset(ScriptDirectory.from_config(alembic_config()).get_heads())


class ReadinessProblem(StrEnum):
    DATABASE_UNREACHABLE = "unreachable"
    MIGRATIONS_PENDING = "pending"


def check_readiness(engine: Engine, expected_heads: frozenset[str]) -> ReadinessProblem | None:
    """Return None when the database answers and is migrated to head, else the problem."""
    try:
        with engine.connect() as conn:
            conn.execute(text(f"SET LOCAL statement_timeout = {READINESS_STATEMENT_TIMEOUT_MS}"))
            conn.execute(text("SELECT 1"))
            current = frozenset(MigrationContext.configure(conn).get_current_heads())
    except SQLAlchemyError as exc:
        # Error type only: driver messages can include host names.
        logger.warning("readiness_db_unreachable", extra={"error_type": type(exc).__name__})
        return ReadinessProblem.DATABASE_UNREACHABLE
    if current != expected_heads:
        logger.warning("readiness_migrations_pending")
        return ReadinessProblem.MIGRATIONS_PENDING
    return None
