"""Application factory and router registration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app.api import health
from app.api.v1 import auth, invites, me, platform
from app.core.config import Settings, get_settings
from app.core.db import create_db_engine
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.mailer import create_mailer
from app.core.middleware import RequestContextMiddleware
from app.core.request_guards import MaxBodySizeMiddleware, OriginCheckMiddleware

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    app.state.engine.dispose()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="CampusSignal API",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json" if settings.docs_enabled else None,
        docs_url=f"{API_PREFIX}/docs" if settings.docs_enabled else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    # Engines connect lazily: creating one does not open a connection.
    app.state.engine = create_db_engine(settings)
    app.state.session_factory = sessionmaker(bind=app.state.engine, expire_on_commit=False)
    app.state.mailer = create_mailer(settings)
    app.state.clock = _utcnow  # tests replace this to exercise expiry rules

    register_error_handlers(app)
    # Added innermost first: a request meets request-context, then the Origin check, then the
    # body-size check, so every rejection still carries a request ID and security headers.
    app.add_middleware(MaxBodySizeMiddleware)
    app.add_middleware(OriginCheckMiddleware, allowed_origin=str(settings.app_origin))
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(me.router, prefix=API_PREFIX)
    app.include_router(invites.router, prefix=API_PREFIX)
    app.include_router(platform.router, prefix=API_PREFIX)
    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn --factory app.main:app_factory`."""
    return create_app()


def __getattr__(name: str) -> FastAPI:
    """Entry point for `uvicorn app.main:app`, built on first access.

    Importing this module must not read settings or `.env` (tests, Alembic and tooling
    import it), so `app` is created lazily from the same factory and then cached.
    """
    if name == "app":
        instance = create_app()
        globals()["app"] = instance
        return instance
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
