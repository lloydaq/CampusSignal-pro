"""Request-level protections applied to every route (architecture.md §10, §13).

- Origin check (PRD AUTH-008): every state-changing request, signed in or not, must carry an
  `Origin` header equal to APP_ORIGIN. A missing, `null` or different Origin gets 403. This
  stops cross-site writes and login CSRF. It is a middleware so a new route cannot forget it.
- Body size: state-changing requests must declare a Content-Length of at most 1 MiB; chunked
  bodies are refused, so an oversized body is never read into memory.
- Client address for rate limits: only as many X-Forwarded-For hops as there are trusted
  proxies are believed.

These are plain ASGI middlewares, so they answer with the standard error envelope directly
(Starlette's exception handlers don't wrap middleware).
"""

from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import error_response

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MAX_BODY_BYTES = 1024 * 1024
_DEFAULT_PORTS = {"http": 80, "https": 443}

Origin = tuple[str, str, int]


def normalize_origin(value: str | None) -> Origin | None:
    """(scheme, host, port) for a bare http(s) origin, else None."""
    if not value:
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if (
        parts.scheme not in _DEFAULT_PORTS
        or not host
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
        or parts.username
    ):
        return None
    return parts.scheme, host.lower(), port or _DEFAULT_PORTS[parts.scheme]


class OriginCheckMiddleware:
    def __init__(self, app: ASGIApp, *, allowed_origin: str) -> None:
        allowed = normalize_origin(allowed_origin)
        if allowed is None:
            raise ValueError("allowed_origin must be a bare http(s) origin")
        self.app = app
        self._allowed = allowed

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            origin = normalize_origin(Headers(scope=scope).get("origin"))
            if origin != self._allowed:
                response = error_response(
                    403, "origin_not_allowed", "This request didn't come from CampusSignal."
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class MaxBodySizeMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            headers = Headers(scope=scope)
            if "transfer-encoding" in headers:
                response = error_response(411, "length_required", "Send a Content-Length header.")
                await response(scope, receive, send)
                return
            declared = headers.get("content-length", "0")
            if not declared.isdigit() or int(declared) > self._max_bytes:
                response = error_response(
                    413, "payload_too_large", "The request body is too large."
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _parse_ip(value: str) -> IPv4Address | IPv6Address | None:
    try:
        return ip_address(value)
    except ValueError:
        return None


def _address_key(address: IPv4Address | IPv6Address) -> str:
    if address.version == 6:
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ip_network(f"{address}/64", strict=False))
    return str(address)


def client_address(request: Request, trusted_proxy_count: int) -> str:
    """Address used for per-client rate limits.

    With N trusted proxies, the N-th entry from the right of X-Forwarded-For is the client
    as the outermost trusted proxy saw it; anything further left is client-controlled and
    ignored. A missing, short or malformed header falls back to the connection's address.
    IPv6 clients share a /64, since a single user can rotate within one.
    """
    peer = request.client.host if request.client else "unknown"
    if trusted_proxy_count > 0:
        forwarded = [
            hop.strip()
            for hop in request.headers.get("x-forwarded-for", "").split(",")
            if hop.strip()
        ]
        if len(forwarded) >= trusted_proxy_count:
            claimed = _parse_ip(forwarded[-trusted_proxy_count])
            if claimed is not None:
                return _address_key(claimed)
    address = _parse_ip(peer)
    # A peer that isn't an IP (test clients, unix sockets) is still a stable, opaque key.
    return peer if address is None else _address_key(address)
