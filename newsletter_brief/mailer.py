"""Send the finished brief to yourself. Uses the same app password as the mailbox."""

from __future__ import annotations

import smtplib
from collections.abc import Callable
from contextlib import AbstractContextManager
from email.message import EmailMessage

class DeliveryError(RuntimeError):
    """Raised when the brief could not be sent. The message does not include secrets."""


SmtpFactory = Callable[[str, int], AbstractContextManager[smtplib.SMTP]]


def _connect(host: str, port: int) -> smtplib.SMTP:
    if port == 465:
        return smtplib.SMTP_SSL(host, port, timeout=30)
    return smtplib.SMTP(host, port, timeout=30)


def send_brief(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    recipient: str,
    subject: str,
    html: str,
    client_factory: SmtpFactory | None = None,
) -> None:
    message = EmailMessage()
    message["From"] = user
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content("Your brief is in the HTML part of this message.")
    message.add_alternative(html, subtype="html")
    factory = client_factory or _connect
    try:
        with factory(host, port) as smtp:
            smtp.debuglevel = 0
            if port != 465:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(message)
    except DeliveryError:
        raise
    except Exception:
        raise DeliveryError("sending the brief failed") from None
