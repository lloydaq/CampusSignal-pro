"""Email delivery (architecture.md §15).

`SmtpMailer` sends through any SMTP server: Mailpit locally, the provider chosen under P-2
in deployments. `InMemoryMailer` keeps messages for tests. Message bodies contain tokens,
so nothing here logs message content or recipients.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings

SMTP_TIMEOUT_SECONDS = 10

logger = logging.getLogger("app.mailer")


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str


class Mailer(Protocol):
    def send(self, email: OutgoingEmail) -> None: ...


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send(self, email: OutgoingEmail) -> None:
        s = self._settings
        message = EmailMessage()
        message["From"] = s.email_from
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.text)

        context = ssl.create_default_context()
        if s.smtp_security == "tls":
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                s.smtp_host, s.smtp_port, timeout=SMTP_TIMEOUT_SECONDS, context=context
            )
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=SMTP_TIMEOUT_SECONDS)
        with server:
            if s.smtp_security == "starttls":
                server.starttls(context=context)
            if s.smtp_username and s.smtp_password:
                server.login(s.smtp_username, s.smtp_password.get_secret_value())
            server.send_message(message)


@dataclass
class InMemoryMailer:
    outbox: list[OutgoingEmail] = field(default_factory=list)

    def send(self, email: OutgoingEmail) -> None:
        self.outbox.append(email)


def create_mailer(settings: Settings) -> Mailer:
    if settings.email_backend == "memory":
        return InMemoryMailer()
    return SmtpMailer(settings)


def send_email(mailer: Mailer, email: OutgoingEmail) -> None:
    """Send in the background after the request's transaction committed.

    A delivery failure must never fail the request, and the log must not reveal who the
    email was for or what it said (it carries tokens), so only the error type is logged.
    """
    try:
        mailer.send(email)
    except Exception as exc:
        logger.error("email_send_failed", extra={"error_type": type(exc).__name__})
