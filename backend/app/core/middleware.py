"""ASGI middleware: request IDs, access logging, baseline security headers, and 500s."""

import logging
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_response
from app.core.request_context import request_id_var

access_logger = logging.getLogger("app.access")
error_logger = logging.getLogger("app.errors")

REQUEST_ID_HEADER = "X-Request-ID"

# Caddy sets the full header set (incl. CSP and HSTS) in deployed environments
# (architecture.md §3); these are the API's own baseline so local and test
# responses carry them too.
SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
}


class RequestContextMiddleware:
    """Assigns a request ID, adds response headers, writes one access log line per request,
    and turns unexpected exceptions into the 500 error envelope.

    The ID is always generated server-side; an incoming X-Request-ID is ignored so
    clients cannot inject values into logs. Unexpected exceptions are handled here
    rather than by Starlette's outermost error middleware so the 500 response still
    carries the request ID and security headers.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code: int | None = None

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            error_logger.exception("unhandled_exception")
            if status_code is not None:
                raise  # response already started; nothing safe to send
            response = error_response(500, "internal_error", "Something went wrong on our side.")
            await response(scope, receive, send_with_headers)
        finally:
            route = scope.get("route")
            access_logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    # Route template, not the raw path: no IDs or query strings in logs.
                    "route": getattr(route, "path", "<unmatched>"),
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)
