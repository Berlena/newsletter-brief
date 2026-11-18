from __future__ import annotations

import logging
import smtplib
import unittest

from newsletter_brief.mailer import DeliveryError, send_brief


class FakeSMTP:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.debuglevel = 99
        self.password = ""
        self.message = None

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def ehlo(self) -> None:
        self.calls.append("ehlo")

    def starttls(self) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append("login")
        self.password = password

    def send_message(self, message: object) -> None:
        self.calls.append("send")
        self.message = message


class MailerTests(unittest.TestCase):
    def test_send_uses_starttls_and_the_html_part(self) -> None:
        fake = FakeSMTP()
        records: list[str] = []
        handler = logging.Handler()
        handler.emit = lambda record: records.append(record.getMessage())  # type: ignore[method-assign]
        logger = logging.getLogger()
        logger.addHandler(handler)
        try:
            send_brief(
                host="smtp.example",
                port=587,
                user="you@example.com",
                password="mailbox-secret-value",
                recipient="you@example.com",
                subject="Your Morning Brief",
                html="<p>Hello</p>",
                client_factory=lambda host, port: fake,
            )
        finally:
            logger.removeHandler(handler)
        self.assertEqual(["ehlo", "starttls", "ehlo", "login", "send"], fake.calls)
        self.assertEqual(0, fake.debuglevel)
        self.assertEqual("mailbox-secret-value", fake.password)
        rendered = fake.message.as_string() if fake.message is not None else ""
        self.assertIn("<p>Hello</p>", rendered)
        self.assertNotIn("mailbox-secret-value", "\n".join(records))

    def test_send_failure_does_not_include_the_password(self) -> None:
        class Boom(FakeSMTP):
            def login(self, user: str, password: str) -> None:
                raise smtplib.SMTPAuthenticationError(535, password.encode())

        with self.assertRaises(DeliveryError) as caught:
            send_brief(
                host="smtp.example",
                port=587,
                user="you@example.com",
                password="mailbox-secret-value",
                recipient="you@example.com",
                subject="Your Morning Brief",
                html="<p>Hello</p>",
                client_factory=lambda host, port: Boom(),
            )
        self.assertNotIn("mailbox-secret-value", str(caught.exception))
        self.assertIn("sending the brief failed", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
