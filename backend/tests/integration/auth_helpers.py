"""Shared helpers for the auth API tests: registering, verifying, signing in, raw SQL."""

import re
from typing import Any

import httpx2
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.core.mailer import InMemoryMailer
from tests.conftest import APP_ORIGIN

EMAIL = "aarav@northfield.example"
PASSWORD = "tidal-quartz-lantern"
NEW_PASSWORD = "copper-meadow-harbour"
NAME = "Aarav Nair"
PREFIX = "/api/v1"
TOKEN_RE = re.compile(r"#token=([A-Za-z0-9_-]+)")


def register(
    client: TestClient, email: str = EMAIL, password: str = PASSWORD, name: str = NAME
) -> httpx2.Response:
    return client.post(
        f"{PREFIX}/auth/register", json={"email": email, "password": password, "display_name": name}
    )


def token_from(mailer: InMemoryMailer, index: int = -1) -> str:
    match = TOKEN_RE.search(mailer.outbox[index].text)
    assert match, "the email has no token link"
    return match.group(1)


def verify(client: TestClient, token: str) -> httpx2.Response:
    return client.post(f"{PREFIX}/auth/verify-email", json={"token": token})


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD) -> httpx2.Response:
    return client.post(f"{PREFIX}/auth/login", json={"email": email, "password": password})


def csrf(client: TestClient) -> dict[str, str]:
    """The X-CSRF-Token header the SPA would send, read from the cs_csrf cookie."""
    token = client.cookies.get("cs_csrf")
    assert token, "not signed in (no cs_csrf cookie)"
    return {"X-CSRF-Token": token}


def create_user(
    client: TestClient,
    mailer: InMemoryMailer,
    *,
    email: str = EMAIL,
    password: str = PASSWORD,
    verified: bool = True,
) -> None:
    """Register through the API (so the password is hashed the real way) and optionally verify."""
    assert register(client, email, password).status_code == 201
    if verified:
        assert verify(client, token_from(mailer)).status_code == 200
    mailer.outbox.clear()


def signed_in(
    app: FastAPI, mailer: InMemoryMailer, *, email: str = EMAIL, password: str = PASSWORD
) -> TestClient:
    """A new browser (own cookie jar) signed in as an already-registered user."""
    client = TestClient(app, raise_server_exceptions=False, headers={"Origin": APP_ORIGIN})
    assert login(client, email, password).status_code == 200
    return client


def sql(conn: Connection, statement: str, **params: Any) -> Any:
    return conn.execute(text(statement), params)


def scalar(conn: Connection, statement: str, **params: Any) -> Any:
    return sql(conn, statement, **params).scalar()


def error_of(response: httpx2.Response) -> dict[str, Any]:
    body = response.json()
    assert set(body) == {"error"}, body
    error: dict[str, Any] = body["error"]
    return error
