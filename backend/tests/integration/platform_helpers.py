"""Clients for the platform-admin and invite tests: each is its own browser (cookie jar)."""

from typing import Any

import httpx2
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import APP_ORIGIN
from tests.integration.auth_helpers import csrf, login
from tests.integration.tenancy import PASSWORD

PLATFORM = "/api/v1/platform"


class Browser:
    """A signed-in browser that sends the CSRF header on writes, like the SPA."""

    def __init__(self, app: FastAPI, email: str | None = None, password: str = PASSWORD) -> None:
        self.client = TestClient(app, raise_server_exceptions=False, headers={"Origin": APP_ORIGIN})
        if email is not None:
            response = login(self.client, email, password)
            assert response.status_code == 200, response.text

    def get(self, path: str, **params: Any) -> httpx2.Response:
        return self.client.get(path, params=params or None)

    def send(self, method: str, path: str, body: dict[str, Any] | None = None) -> httpx2.Response:
        headers = csrf(self.client) if self.client.cookies.get("cs_csrf") else {}
        return self.client.request(method, path, json=body, headers=headers)

    def post(self, path: str, body: dict[str, Any] | None = None) -> httpx2.Response:
        return self.send("POST", path, body)

    def patch(self, path: str, body: dict[str, Any]) -> httpx2.Response:
        return self.send("PATCH", path, body)
