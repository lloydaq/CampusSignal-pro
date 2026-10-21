"""Application factory and router registration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app.api import health
from app.core.config import Settings, get_settings
from app.core.db import create_db_engine
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    app.state.engine.dispose()


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

    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
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
