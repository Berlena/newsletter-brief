from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from newsletter_brief.cli import main


class CliTests(unittest.TestCase):
    def test_offline_command_writes_html_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "nested" / "index.html"
            stdout = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), redirect_stdout(stdout):
                result = main(["demo", "--offline", "--output", str(output)])
            self.assertEqual(0, result)
            self.assertTrue(output.exists())
            self.assertIn("offline synthetic demo", stdout.getvalue())
            self.assertIn("<!doctype html>", output.read_text())

    def test_live_command_lists_missing_variables(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "index.html"
            stderr = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), redirect_stderr(stderr):
                result = main(["demo", "--live", "--output", str(output)])
            self.assertEqual(2, result)
            self.assertFalse(output.exists())
            self.assertIn("LLM settings are missing: LLM_MODEL, LLM_API_KEY", stderr.getvalue())

    def test_offline_command_refuses_a_brief_with_an_invented_link(self) -> None:
        ungrounded = Path(__file__).resolve().parents[1] / "demo" / "ungrounded_response.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "index.html"
            stderr = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), redirect_stderr(stderr):
                result = main(
                    [
                        "demo",
                        "--offline",
                        "--prepared-response",
                        str(ungrounded),
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(2, result)
            self.assertFalse(output.exists())
            self.assertIn("absent from the input feed", stderr.getvalue())
            self.assertIn("https://invented-source.example/", stderr.getvalue())

    def test_senders_command_prints_domains_without_a_model(self) -> None:
        from email.message import EmailMessage

        messages = {}

        def _raw(sender: str, subject: str) -> bytes:
            message = EmailMessage()
            message["From"] = sender
            message["Subject"] = subject
            message["Date"] = "Wed, 18 Nov 2026 07:00:00 +0000"
            message.set_content("Body that must not be printed.")
            return message.as_bytes()

        messages[b"1"] = _raw("Harbor Daily <desk@harbor-daily.example>", "Secret subject")
        messages[b"2"] = _raw("Other <person@other.example>", "Another secret subject")
        messages[b"3"] = _raw("Harbor Daily <ed@harbor-daily.example>", "Third secret subject")

        class Fake:
            def __init__(self) -> None:
                self.messages = messages

            def login(self, user: str, password: str) -> str:
                return "OK"

            def select(self, folder: str, readonly: bool = False) -> tuple[str, list[bytes]]:
                self.folder = (folder, readonly)
                return "OK", [b"3"]

            def search(self, charset: object, *criteria: str) -> tuple[str, list[bytes]]:
                return "OK", [b"1 2 3"]

            def fetch(self, num: bytes, what: str) -> tuple[str, list[object]]:
                self.what = what
                raw = self.messages[num]
                meta = b'%b (INTERNALDATE "18-Nov-2026 07:00:00 +0000" BODY[] {%d}' % (num, len(raw))
                return "OK", [(meta, raw), b")"]

            def logout(self) -> tuple[str, list[bytes]]:
                return "BYE", []

        fake = Fake()

        def connector(host: str, port: int) -> Fake:
            return fake

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            path.write_text(
                """
[mailbox]
host = "imap.example"
user = "you@example.com"
folder = "Newsletters"
hours = 24
[senders]
mode = "folder"
[output]
path = "brief.html"
[figures]
show = []
""",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            env = {"NEWSLETTER_BRIEF_MAILBOX_PASSWORD": "mailbox-secret-value"}
            with (
                patch.dict(os.environ, env, clear=True),
                patch("newsletter_brief.inbox._default_connector", connector),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                result = main(["senders", "--config", str(path), "--hours", "720"])
        self.assertEqual(0, result, stderr.getvalue())
        self.assertEqual("harbor-daily.example 2\nother.example 1\n", stdout.getvalue())
        self.assertNotIn("Secret", stdout.getvalue())
        self.assertNotIn("Body", stdout.getvalue())
        self.assertNotIn("@", stdout.getvalue())
        self.assertIn("PEEK", fake.what)
        self.assertTrue(fake.folder[1])


if __name__ == "__main__":
    unittest.main()
