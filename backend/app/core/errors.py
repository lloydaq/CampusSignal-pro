"""Domain exceptions and the single error envelope (architecture.md §12).

Every non-2xx response has the shape:
    {"error": {"code": str, "message": str, "details": ... | null, "request_id": str | null}}
"""

from collections.abc import Mapping
from typing import Any, ClassVar, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import current_request_id


class AppError(Exception):
    """Base class for errors raised by services and mapped to the envelope."""

    status_code: ClassVar[int] = 400
    code: ClassVar[str] = "bad_request"
    default_message: ClassVar[str] = "The request could not be processed."

    def __init__(
        self, message: str | None = None, *, code: str | None = None, details: Any = None
    ) -> None:
        self.message = message or self.default_message
        self.error_code = code or self.code
        self.details = details
        super().__init__(self.message)


class BadRequest(AppError):
    pass


class NotAuthenticated(AppError):
    status_code = 401
    code = "not_authenticated"
    default_message = "Sign in to continue."


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"
    default_message = "You don't have access to this."


class NotFound(AppError):
    """Also used for objects in another college or not readable by the actor (Rules R-2.4)."""

    status_code = 404
    code = "not_found"
    default_message = "Not found."


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    default_message = "The request conflicts with the current state."


class NotReady(AppError):
    status_code = 503
    code = "not_ready"
    default_message = "The service is not ready."


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    default_message = "Too many requests. Try again later."

    def __init__(self, retry_after_seconds: int, message: str | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": current_request_id(),
        }
    }
    return JSONResponse(status_code=status_code, content=body, headers=headers)


_HTTP_STATUS_CODES: dict[int, tuple[str, str]] = {
    404: ("not_found", NotFound.default_message),
    405: ("method_not_allowed", "This method is not allowed for this resource."),
}


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    exc = cast(AppError, exc)  # registered for AppError only
    headers = None
    if isinstance(exc, RateLimited):
        headers = {"Retry-After": str(exc.retry_after_seconds)}
    return error_response(exc.status_code, exc.error_code, exc.message, exc.details, headers)


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    exc = cast(RequestValidationError, exc)  # registered for this type only
    # Only field location and message: never echo the submitted input back,
    # it may contain passwords or other sensitive values.
    details = [
        {
            "field": ".".join(str(part) for part in err.get("loc", ()) if part != "body"),
            "message": err.get("msg", "Invalid value."),
        }
        for err in exc.errors()
    ]
    return error_response(422, "validation_error", "Some fields are invalid.", details)


async def _handle_http_exception(_: Request, exc: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, exc)  # registered for this type only
    code, message = _HTTP_STATUS_CODES.get(exc.status_code, ("http_error", "Request failed."))
    return error_response(exc.status_code, code, message, headers=exc.headers)


def register_error_handlers(app: FastAPI) -> None:
    """Expected errors. Unexpected exceptions become 500s in RequestContextMiddleware."""
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
