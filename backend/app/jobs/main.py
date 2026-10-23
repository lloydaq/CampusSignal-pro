"""`python -m app.jobs run-due`: everything that is due, run hourly by the scheduler.

Today that is the retention purges. It writes one JSON log line per purge with the number
of rows deleted (never row contents) and exits non-zero if any purge failed, so the
scheduler can alert.
"""

import argparse
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import create_db_engine
from app.core.logging import configure_logging
from app.services.retention import run_purges

logger = logging.getLogger("app.jobs")

EXIT_OK = 0
EXIT_FAILED = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.jobs", description="CampusSignal jobs.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run-due", help="run every due job (retention purges)")
    return parser


def run_due(settings: Settings, session_factory: Callable[[], Session], now: datetime) -> int:
    failed = False
    for outcome in run_purges(session_factory, settings, now):
        if outcome.error_type is None:
            logger.info(
                "retention_purge", extra={"purge": outcome.name, "deleted": outcome.deleted}
            )
        else:
            failed = True
            logger.error(
                "retention_purge_failed",
                extra={"purge": outcome.name, "error_type": outcome.error_type},
            )
    return EXIT_FAILED if failed else EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    session_factory: Callable[[], Session] | None = None,
    now: datetime | None = None,
) -> int:
    build_parser().parse_args(argv)  # run-due is the only command
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    when = now or datetime.now(UTC)
    if session_factory is not None:
        return run_due(settings, session_factory, when)

    engine = create_db_engine(settings)
    try:
        return run_due(settings, sessionmaker(bind=engine, expire_on_commit=False), when)
    finally:
        engine.dispose()
