"""Mailers: in-memory for tests, SMTP for Mailpit and deployments. No network."""

from typing import Any, ClassVar

import pytest

from app.core.mailer import InMemoryMailer, OutgoingEmail, SmtpMailer, create_mailer
from tests.conftest import make_settings

EMAIL = OutgoingEmail(to="aarav@northfield.example", subject="Verify", text="Link: #token=abc")


class FakeSMTP:
    instances: ClassVar[list["FakeSMTP"]] = []

    def __init__(self, host: str, port: int, **kwargs: Any) -> None:
        self.host, self.port, self.kwargs = host, port, kwargs
        self.calls: list[str] = []
        self.sent: list[Any] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *exc: object) -> None:
        self.calls.append("quit")

    def starttls(self, **kwargs: Any) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login:{user}:{password}")

    def send_message(self, message: Any) -> None:
        self.calls.append("send")
        self.sent.append(message)


@pytest.fixture(autouse=True)
def _fake_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("smtplib.SMTP_SSL", FakeSMTP)


def test_create_mailer_picks_backend() -> None:
    assert isinstance(create_mailer(make_settings(email_backend="memory")), InMemoryMailer)
    assert isinstance(create_mailer(make_settings(email_backend="smtp")), SmtpMailer)


def test_in_memory_mailer_collects_messages() -> None:
    mailer = InMemoryMailer()
    mailer.send(EMAIL)
    assert mailer.outbox == [EMAIL]


def test_smtp_plain_for_local_mailpit() -> None:
    SmtpMailer(make_settings(email_backend="smtp")).send(EMAIL)
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("localhost", 1025)
    assert smtp.calls == ["send", "quit"]
    message = smtp.sent[0]
    assert message["To"] == EMAIL.to
    assert message["Subject"] == "Verify"
    assert message["From"] == "CampusSignal <no-reply@campussignal.localhost>"
    assert "#token=abc" in message.get_content()


def test_smtp_starttls_then_login() -> None:
    settings = make_settings(
        email_backend="smtp",
        smtp_host="smtp.example",
        smtp_port=587,
        smtp_security="starttls",
        smtp_username="mailer",
        smtp_password="smtp-s3cret",
    )
    SmtpMailer(settings).send(EMAIL)
    assert FakeSMTP.instances[0].calls == ["starttls", "login:mailer:smtp-s3cret", "send", "quit"]


def test_smtp_implicit_tls_uses_ssl_context() -> None:
    SmtpMailer(make_settings(email_backend="smtp", smtp_security="tls", smtp_port=465)).send(EMAIL)
    smtp = FakeSMTP.instances[0]
    assert "context" in smtp.kwargs
    assert smtp.calls == ["send", "quit"]
