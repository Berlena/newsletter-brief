from __future__ import annotations

import threading
import unittest
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from newsletter_brief.inbox import (
    InboxError,
    clean_url,
    default_head,
    extract_links,
    read_eml_directory,
    read_imap,
    resolve_redirect,
    sender_allowed,
)
from own_inbox_samples import LETTERS, eml_bytes, write_sample_mail

NOW = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)


class SenderTests(unittest.TestCase):
    def test_exact_address_domain_and_case(self) -> None:
        allow = ("desk@harbor-daily.example", "canopy-notes.example")
        self.assertTrue(sender_allowed("Desk@Harbor-Daily.example", allow))
        self.assertTrue(sender_allowed("ed@canopy-notes.example", allow))
        self.assertTrue(sender_allowed("news@letters.canopy-notes.example", allow))
        self.assertFalse(sender_allowed("ed@other.example", allow))
        self.assertFalse(sender_allowed("not-an-address", allow))
        self.assertFalse(sender_allowed("", allow))


class LinkTests(unittest.TestCase):
    def test_tracking_parameters_are_removed_and_real_ones_stay(self) -> None:
        cleaned = clean_url(
            "https://harbor-daily.example/library-vote?utm_source=newsletter&id=3&UTM_MEDIUM=email"
        )
        self.assertEqual("https://harbor-daily.example/library-vote?id=3", cleaned)

    def test_embedded_redirect_is_unwrapped_without_a_request(self) -> None:
        cleaned = clean_url(
            "https://clicks.example/r?url=https%3A%2F%2Fharbor-daily.example%2Flibrary-vote%3Futm_source%3Dnl"
        )
        self.assertEqual("https://harbor-daily.example/library-vote", cleaned)

    def test_unsafe_links_are_dropped(self) -> None:
        self.assertIsNone(clean_url("mailto:desk@harbor-daily.example"))
        self.assertIsNone(clean_url("javascript:alert(1)"))
        self.assertIsNone(clean_url("http://harbor-daily.example/library-vote"))
        self.assertIsNone(clean_url("https://" + "127.0.0.1/library-vote"))
        self.assertIsNone(clean_url("https://" + "user:pass@harbor-daily.example/story"))

    def test_html_and_plain_text_extraction(self) -> None:
        html = """
        <html><body>
          <a href="mailto:desk@harbor-daily.example">unsubscribe from this list</a>
          <a href="https://harbor-daily.example/library-vote?utm_source=nl">Library budget vote</a>
          <p>See also https://harbor-daily.example/minutes</p>
        </body></html>
        """
        plain = "Plain copy https://harbor-daily.example/minutes and https://canopy-notes.example/river-gauge"
        links = extract_links(
            html,
            plain,
            subject="Library budget vote is on Thursday",
            max_chars=500,
        )
        urls = [item[0] for item in links]
        self.assertEqual(
            [
                "https://harbor-daily.example/library-vote",
                "https://harbor-daily.example/minutes",
                "https://canopy-notes.example/river-gauge",
            ],
            urls,
        )
        self.assertEqual("Library budget vote", links[0][1])

    def test_known_redirect_host_uses_the_head_hook_once(self) -> None:
        calls: list[str] = []

        def head(url: str) -> str:
            calls.append(url)
            return "https://harbor-daily.example/library-vote?utm_source=nl"

        tracker = "https://" + "track.list-manage.com/click?id=9"
        resolved = resolve_redirect(tracker, head)
        self.assertEqual([tracker], calls)
        self.assertEqual("https://harbor-daily.example/library-vote", resolved)

        calls.clear()
        kept = resolve_redirect("https://harbor-daily.example/library-vote", head)
        self.assertEqual([], calls)
        self.assertEqual("https://harbor-daily.example/library-vote", kept)

    def test_a_failed_redirect_keeps_the_original_link(self) -> None:
        def head(url: str) -> str:
            raise TimeoutError(url)

        original = "https://" + "track.list-manage.com/click?id=9"
        self.assertEqual(original, resolve_redirect(original, head))

    def test_default_head_reads_one_location_and_stops(self) -> None:
        seen: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def do_HEAD(self) -> None:  # noqa: N802
                seen.append(self.command)
                self.send_response(302)
                self.send_header("Location", "https://harbor-daily.example/library-vote")
                self.end_headers()

            def do_GET(self) -> None:  # noqa: N802
                seen.append(self.command)
                self.send_response(200)
                self.end_headers()

            def log_message(self, fmt: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            target = default_head(f"http://127.0.0.1:{port}/click")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual("https://harbor-daily.example/library-vote", target)
        self.assertEqual(["HEAD"], seen)


class FakeIMAP:
    def __init__(self, messages: dict[bytes, bytes]) -> None:
        self.messages = messages
        self.calls: list[tuple[object, ...]] = []

    def login(self, user: str, password: str) -> str:
        self.calls.append(("login", user))
        self.password = password
        return "OK"

    def select(self, folder: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        self.calls.append(("select", folder, readonly))
        return "OK", [str(len(self.messages)).encode()]

    def search(self, charset: object, *criteria: str) -> tuple[str, list[bytes]]:
        self.calls.append(("search", criteria))
        return "OK", [b" ".join(self.messages)]

    def fetch(self, num: bytes, what: str) -> tuple[str, list[object]]:
        self.calls.append(("fetch", what))
        if "PEEK" not in what.upper():
            raise AssertionError(what)
        raw = self.messages[num]
        meta = (
            b'%b (INTERNALDATE "18-Nov-2026 07:00:00 +0000" BODY[] {%d}'
            % (num, len(raw))
        )
        return "OK", [(meta, raw), b")"]

    def store(self, *args: object) -> None:
        raise AssertionError("store was called")

    def expunge(self) -> None:
        raise AssertionError("expunge was called")

    def logout(self) -> tuple[str, list[bytes]]:
        self.calls.append(("logout",))
        return "BYE", []


def _message(sender: str, subject: str, href: str, when: str) -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "you@example.com"
    message["Subject"] = subject
    message["Date"] = when
    message.set_content("Plain text with no extra link.")
    message.add_alternative(
        f'<html><body><p>{subject}</p><a href="{href}">Read the piece</a></body></html>',
        subtype="html",
    )
    return message.as_bytes()


class ImapTests(unittest.TestCase):
    def test_readonly_peek_and_sender_filter(self) -> None:
        messages = {
            b"1": _message(
                "Harbor Daily <desk@harbor-daily.example>",
                "Library budget vote is on Thursday",
                "https://harbor-daily.example/library-vote?utm_source=nl",
                "Wed, 18 Nov 2026 07:00:00 +0000",
            ),
            b"2": _message(
                "Other <person@other.example>",
                "Ignore this one",
                "https://other.example/secret-story",
                "Wed, 18 Nov 2026 07:05:00 +0000",
            ),
            b"3": _message(
                "Harbor Daily <desk@harbor-daily.example>",
                "An old letter",
                "https://harbor-daily.example/old-letter",
                "Mon, 02 Nov 2026 07:00:00 +0000",
            ),
        }
        fake = FakeIMAP(messages)

        def connector(host: str, port: int) -> FakeIMAP:
            self.assertEqual("imap.example", host)
            self.assertEqual(993, port)
            return fake

        collected = read_imap(
            host="imap.example",
            port=993,
            user="you@example.com",
            password="mailbox-secret-value",
            folder="INBOX",
            hours=24,
            allowlist=("harbor-daily.example",),
            max_messages=30,
            max_chars=2000,
            max_total_chars=60000,
            now=NOW,
            connector=connector,
            head=None,
        )
        urls = [item.source_url for item in collected.items]
        self.assertEqual(["https://harbor-daily.example/library-vote"], urls)
        self.assertNotIn("https://other.example/secret-story", urls)
        self.assertNotIn("https://harbor-daily.example/old-letter", urls)
        self.assertIn(("select", "INBOX", True), fake.calls)
        self.assertTrue(any(call[0] == "fetch" and "PEEK" in str(call[1]) for call in fake.calls))
        self.assertNotIn("store", [call[0] for call in fake.calls])
        self.assertEqual("Harbor Daily", collected.items[0].publication)
        self.assertNotIn("mailbox-secret-value", collected.items[0].excerpt)

    def test_login_failure_does_not_repeat_the_password(self) -> None:
        class BadIMAP(FakeIMAP):
            def login(self, user: str, password: str) -> str:
                raise RuntimeError(f"nope {password}")

        def connector(host: str, port: int) -> BadIMAP:
            return BadIMAP({})

        with self.assertRaises(InboxError) as caught:
            read_imap(
                host="imap.example",
                port=993,
                user="you@example.com",
                password="mailbox-secret-value",
                folder="INBOX",
                hours=24,
                allowlist=("harbor-daily.example",),
                max_messages=10,
                max_chars=1000,
                max_total_chars=5000,
                now=NOW,
                connector=connector,
            )
        self.assertEqual("mailbox login failed", str(caught.exception))
        self.assertNotIn("mailbox-secret-value", str(caught.exception))


class EmlTests(unittest.TestCase):
    def test_folder_of_five_letters_keeps_allowlisted_recent_mail(self) -> None:
        folder = Path(self.id().replace(".", "_"))
        # Use a temp dir so the files are not inside the repo.
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            write_sample_mail(path)
            old = dict(LETTERS[0])
            raw = eml_bytes(old).replace(
                b"Date: Wed, 18 Nov 2026 07:00:00 +0000",
                b"Date: Mon, 02 Nov 2026 07:00:00 +0000",
            )
            raw = raw.replace(b"desk@harbor-daily.example", b"person@other.example")
            (path / "99-other.eml").write_bytes(raw)
            collected = read_eml_directory(
                path,
                allowlist=tuple(letter["address"].split("@", 1)[1] for letter in LETTERS),
                hours=24,
                max_chars=2000,
                max_total_chars=60000,
                now=NOW,
                head=None,
            )
        self.assertEqual(5, len(collected.items))
        self.assertEqual(
            [letter["url"] for letter in LETTERS],
            [item.source_url for item in collected.items],
        )
        self.assertGreaterEqual(collected.skipped_senders, 1)
        self.assertNotIn("other.example", " ".join(item.source_url for item in collected.items))

    def test_old_mail_is_outside_the_window(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "old.eml"
            path.write_bytes(
                eml_bytes(LETTERS[0]).replace(
                    b"Date: Wed, 18 Nov 2026 07:00:00 +0000",
                    b"Date: Mon, 02 Nov 2026 07:00:00 +0000",
                )
            )
            collected = read_eml_directory(
                Path(temp),
                allowlist=("harbor-daily.example",),
                hours=24,
                max_chars=2000,
                max_total_chars=60000,
                now=NOW,
                head=None,
            )
        self.assertEqual((), collected.items)


if __name__ == "__main__":
    unittest.main()
