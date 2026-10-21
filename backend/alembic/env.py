"""Alembic environment: connection settings come from app settings, never from alembic.ini."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, Engine

from app.core.config import get_settings
from app.core.db import Base, create_db_engine

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout (`alembic upgrade head --sql`) without connecting."""
    context.configure(
        url=get_settings().database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_with_connection(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests may pass an open connection via config.attributes["connection"].
    connection: Connection | None = config.attributes.get("connection")
    if connection is not None:
        _run_with_connection(connection)
        return
    engine: Engine = create_db_engine(get_settings())
    try:
        with engine.connect() as conn:
            _run_with_connection(conn)
            conn.commit()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
