"""Application factory and router registration."""

from fastapi import FastAPI

from app.api import health
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="CampusSignal API",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json" if settings.docs_enabled else None,
        docs_url=f"{API_PREFIX}/docs" if settings.docs_enabled else None,
        redoc_url=None,
    )
    app.state.settings = settings

    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn --factory app.main:app_factory`."""
    return create_app()
