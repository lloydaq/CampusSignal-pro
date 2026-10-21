"""DATABASE_URL validation and secrecy. No database or network needed."""

import pytest
from pydantic import ValidationError

from app.core.db import create_db_engine
from tests.conftest import disposable_database_problem, is_hosted_supabase, make_settings

PASSWORD = "s3cret-Pa55word"
SUPABASE_POOLER = (
    f"postgresql+psycopg://postgres.abcdefgh:{PASSWORD}"
    "@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
)


def test_remote_database_requires_ssl() -> None:
    with pytest.raises(ValidationError, match="sslmode=require") as exc:
        make_settings(database_url=SUPABASE_POOLER)
    assert PASSWORD not in str(exc.value)


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer"])
def test_remote_database_rejects_weak_sslmode(mode: str) -> None:
    with pytest.raises(ValidationError, match="sslmode=require"):
        make_settings(database_url=f"{SUPABASE_POOLER}?sslmode={mode}")


@pytest.mark.parametrize("mode", ["require", "verify-ca", "verify-full"])
def test_remote_database_accepts_secure_sslmode(mode: str) -> None:
    settings = make_settings(database_url=f"{SUPABASE_POOLER}?sslmode={mode}")
    assert settings.database_url.get_secret_value().endswith(mode)


def test_local_database_may_skip_ssl() -> None:
    make_settings(database_url="postgresql+psycopg://u:p@localhost:5432/campussignal")


@pytest.mark.parametrize(
    "url",
    [
        f"postgresql://postgres:{PASSWORD}@localhost/db",  # default driver is psycopg2
        f"postgresql+asyncpg://postgres:{PASSWORD}@localhost/db",
        f"sqlite:///{PASSWORD}.db",
        "not a url",
    ],
)
def test_database_url_must_use_psycopg_driver(url: str) -> None:
    with pytest.raises(ValidationError) as exc:
        make_settings(database_url=url)
    assert PASSWORD not in str(exc.value)
    assert PASSWORD not in repr(exc.value)


def test_database_url_never_shown_in_settings_output() -> None:
    settings = make_settings(database_url=f"{SUPABASE_POOLER}?sslmode=require")
    assert PASSWORD not in repr(settings)
    assert PASSWORD not in str(settings)
    assert PASSWORD not in str(settings.model_dump())


def test_engine_repr_hides_password() -> None:
    engine = create_db_engine(make_settings(database_url=f"{SUPABASE_POOLER}?sslmode=require"))
    try:
        assert PASSWORD not in repr(engine)
        assert PASSWORD not in str(engine.url)
    finally:
        engine.dispose()


def test_engine_hides_bound_parameters_in_errors() -> None:
    engine = create_db_engine(make_settings())
    try:
        assert engine.hide_parameters is True
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("url", "hosted"),
    [
        ("postgresql+psycopg://u:p@aws-0-ap-south-1.pooler.supabase.com:5432/postgres", True),
        ("postgresql+psycopg://u:p@db.abcdefgh.supabase.co:5432/postgres", True),
        ("postgresql+psycopg://u:p@DB.ABCDEFGH.SUPABASE.CO.:5432/postgres", True),
        ("postgresql+psycopg://u:p@localhost:5432/campussignal_test", False),
        ("postgresql+psycopg://u:p@127.0.0.1:5432/campussignal_test", False),
        ("postgresql+psycopg://u:p@notsupabase.co.example:5432/db", False),
    ],
)
def test_integration_guard_recognises_supabase_hosts(url: str, hosted: bool) -> None:
    assert is_hosted_supabase(url) is hosted


@pytest.mark.parametrize(
    ("url", "accepted"),
    [
        ("postgresql+psycopg://postgres@localhost:5432/campussignal_test", True),
        ("postgresql+psycopg://postgres@127.0.0.1:5432/campussignal_test", True),
        ("postgresql+psycopg://postgres@localhost:5432/campussignal", False),  # not *_test
        ("postgresql+psycopg://postgres@localhost:5432/postgres", False),
        ("postgresql+psycopg://u:p@db.abcdefgh.supabase.co:5432/x_test", False),
        ("postgresql+psycopg://u:p@aws-0-x.pooler.supabase.com:5432/x_test", False),
        ("postgresql+psycopg://u:p@db.internal.example:5432/x_test", False),  # not loopback
        ("not a url", False),
    ],
)
def test_destructive_tests_require_positively_disposable_database(url: str, accepted: bool) -> None:
    problem = disposable_database_problem(url)
    assert (problem is None) is accepted
    if problem is not None:
        assert "p@" not in problem and "supabase.co:" not in problem  # never echoes the URL
