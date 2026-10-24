"""`python -m app.cli create-platform-admin --email ... --display-name ...` (ADMIN-005) and
`python -m app.cli seed-demo` (demo data, local/ci only).

The password is only ever read from the terminal (typed twice, not echoed): never from an
argument or environment variable, which would leave it in shell history or the process list.
Output names the new account by ID only.
"""

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import TextIO

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import create_db_engine
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.services import demo_seed, platform_admins

SessionFactory = Callable[[], Session]
PasswordReader = Callable[[str], str]

EXIT_OK = 0
EXIT_FAILED = 1

# Demo data is for development and CI only: it creates accounts with a shared password.
DEMO_ENVIRONMENTS = ("local", "ci")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli", description="CampusSignal operator commands."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser(
        "create-platform-admin",
        help="create a new platform-admin account (the password is prompted for)",
    )
    create.add_argument("--email", required=True)
    create.add_argument("--display-name", required=True)
    commands.add_parser(
        "seed-demo",
        help="add the fictional demo colleges and accounts (local/ci only; prompts for a password)",
    )
    return parser


def _describe(error: AppError) -> str:
    if isinstance(error.details, list):
        return " ".join(f"{d['field']}: {d['message']}" for d in error.details)
    return error.message


def create_platform_admin(
    args: argparse.Namespace,
    *,
    session_factory: SessionFactory,
    read_password: PasswordReader,
    now: datetime,
    out: TextIO,
) -> int:
    try:
        # Check the cheap inputs before asking for a password.
        platform_admins.clean_identity(email=args.email, display_name=args.display_name)
        password = read_password("Password: ")
        if read_password("Repeat password: ") != password:
            print("Passwords do not match. Nothing was created.", file=out)
            return EXIT_FAILED
        with session_factory() as db:
            user = platform_admins.create_platform_admin(
                db,
                email=args.email,
                display_name=args.display_name,
                password=password,
                now=now,
            )
    except AppError as exc:
        print(f"{_describe(exc)} Nothing was created.", file=out)
        return EXIT_FAILED
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. Nothing was created.", file=out)
        return EXIT_FAILED
    print(f"Created platform admin {user.id}.", file=out)
    return EXIT_OK


def seed_demo(
    args: argparse.Namespace,
    *,
    session_factory: SessionFactory,
    read_password: PasswordReader,
    now: datetime,
    out: TextIO,
) -> int:
    try:
        password = read_password("Password for the demo accounts: ")
        if read_password("Repeat password: ") != password:
            print("Passwords do not match. Nothing was created.", file=out)
            return EXIT_FAILED
        with session_factory() as db:
            report = demo_seed.seed_demo(db, password=password, now=now)
    except AppError as exc:
        print(f"{_describe(exc)} Nothing was created.", file=out)
        return EXIT_FAILED
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. Nothing was created.", file=out)
        return EXIT_FAILED
    print(
        f"Added {report.colleges} colleges, {report.departments} departments, "
        f"{report.accounts} accounts and {report.roster_entries} roster entries. "
        "The demo accounts and roll numbers are listed in app/services/demo_seed.py.",
        file=out,
    )
    return EXIT_OK


def _refuse_demo(app_env: str, out: TextIO) -> int:
    print(f"seed-demo only runs with APP_ENV=local or ci, not {app_env}.", file=out)
    return EXIT_FAILED


def main(
    argv: Sequence[str] | None = None,
    *,
    app_env: str = "local",
    session_factory: SessionFactory | None = None,
    read_password: PasswordReader = getpass.getpass,
    now: datetime | None = None,
    out: TextIO | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    run = {"create-platform-admin": create_platform_admin, "seed-demo": seed_demo}[args.command]
    when = now or datetime.now(UTC)
    stream = out or sys.stdout
    if session_factory is not None:
        if args.command == "seed-demo" and app_env not in DEMO_ENVIRONMENTS:
            return _refuse_demo(app_env, stream)
        return run(
            args, session_factory=session_factory, read_password=read_password, now=when, out=stream
        )

    settings = get_settings()
    if args.command == "seed-demo" and settings.app_env not in DEMO_ENVIRONMENTS:
        return _refuse_demo(settings.app_env, stream)
    configure_logging(settings.log_level)
    engine = create_db_engine(settings)
    try:
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        return run(args, session_factory=factory, read_password=read_password, now=when, out=stream)
    finally:
        engine.dispose()
