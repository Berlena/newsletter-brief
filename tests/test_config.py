from __future__ import annotations

import unittest
from pathlib import Path

from newsletter_brief.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_example_file_loads(self) -> None:
        config = load_config(ROOT / "config.example.toml")
        self.assertEqual("Your Morning Brief", config.title)
        self.assertEqual(24, config.mailbox.hours)
        self.assertEqual(993, config.mailbox.port)
        self.assertEqual("you@example.com", config.mailbox.user)
        self.assertEqual(("eur-usd", "eur-gbp", "btc-usd", "eth-usd"), config.figures)
        self.assertFalse(config.delivery.enabled)
        self.assertEqual(("city services", "climate"), config.topics)
        self.assertTrue(str(config.output_path).endswith("output/brief.html"))
        self.assertEqual("allow", config.sender_mode)
        self.assertTrue(config.mailbox.unread_only)
        self.assertEqual((), config.sections)
        self.assertEqual((), config.feeds)
        self.assertFalse(config.articles.enabled)
        self.assertFalse(config.context.lookup)
        self.assertEqual(5, config.fact_count)
        self.assertEqual(2, config.memory.days)

    def test_hours_default_when_omitted(self) -> None:
        text = """
title = "Brief"
[mailbox]
host = "imap.example"
user = "you@example.com"
[senders]
allow = ["news.example"]
[output]
path = "brief.html"
[figures]
show = []
"""
        path = self._write(text)
        config = load_config(path)
        self.assertEqual(24, config.mailbox.hours)
        self.assertEqual((), config.figures)

    def test_password_field_is_rejected(self) -> None:
        text = (ROOT / "config.example.toml").read_text(encoding="utf-8")
        text += '\npassword = "do-not-store-this"\n'
        with self.assertRaisesRegex(ConfigError, "not allowed in the config file"):
            load_config(self._write(text))

    def test_secret_shaped_value_is_rejected(self) -> None:
        forged = "sk-" + ("b" * 20)
        text = (ROOT / "config.example.toml").read_text(encoding="utf-8")
        text = text.replace("city services", forged)
        with self.assertRaisesRegex(ConfigError, "looks like a secret"):
            load_config(self._write(text))

    def test_unknown_figure_is_rejected(self) -> None:
        text = (ROOT / "config.example.toml").read_text(encoding="utf-8")
        text = text.replace('"eur-usd"', '"sp500"')
        with self.assertRaisesRegex(ConfigError, "eur-xxx"):
            load_config(self._write(text))

    def test_empty_sender_list_is_rejected(self) -> None:
        text = """
[mailbox]
host = "imap.example"
user = "you@example.com"
[senders]
allow = []
[output]
path = "brief.html"
"""
        with self.assertRaisesRegex(ConfigError, "at least one"):
            load_config(self._write(text))

    def test_unknown_section_is_rejected(self) -> None:
        text = (ROOT / "config.example.toml").read_text(encoding="utf-8")
        text += "\n[ranking]\nmode = \"private\"\n"
        with self.assertRaisesRegex(ConfigError, "unknown config fields"):
            load_config(self._write(text))

    def test_enabled_delivery_needs_a_host(self) -> None:
        text = """
[mailbox]
host = "imap.example"
user = "you@example.com"
[senders]
allow = ["news.example"]
[output]
path = "brief.html"
[delivery]
enabled = true
"""
        with self.assertRaisesRegex(ConfigError, "smtp_host"):
            load_config(self._write(text))

    def test_output_path_is_relative_to_the_config_file(self) -> None:
        folder = Path(self._write("placeholder")).parent
        path = folder / "nested" / "config.toml"
        path.parent.mkdir()
        path.write_text(
            """
[mailbox]
host = "imap.example"
user = "you@example.com"
[senders]
allow = ["news.example"]
[output]
path = "out/brief.html"
[figures]
show = []
""",
            encoding="utf-8",
        )
        config = load_config(path)
        self.assertEqual((folder / "nested" / "out" / "brief.html").resolve(), config.output_path)

    def test_folder_mode_needs_a_dedicated_folder(self) -> None:
        base = """
[mailbox]
host = "imap.example"
user = "you@example.com"
folder = "FOLDER"
[senders]
mode = "folder"
[output]
path = "brief.html"
[figures]
show = []
"""
        config = load_config(self._write(base.replace("FOLDER", "Newsletters")))
        self.assertEqual("folder", config.sender_mode)
        self.assertEqual((), config.senders)
        for name in ("INBOX", "inbox", "Inbox"):
            with self.assertRaisesRegex(ConfigError, "INBOX"):
                load_config(self._write(base.replace("FOLDER", name)))
        nested = load_config(self._write(base.replace("FOLDER", "INBOX/Newsletters")))
        self.assertEqual("INBOX/Newsletters", nested.mailbox.folder)

    def test_folder_mode_rejects_an_allow_list(self) -> None:
        text = """
[mailbox]
host = "imap.example"
user = "you@example.com"
folder = "Newsletters"
[senders]
mode = "folder"
allow = ["news.example"]
[output]
path = "brief.html"
"""
        with self.assertRaisesRegex(ConfigError, "not used"):
            load_config(self._write(text))

    def test_sections_days_and_feeds(self) -> None:
        text = """
[mailbox]
host = "imap.example"
user = "you@example.com"
folder = "INBOX"
unread_only = false
[senders]
allow = ["news.example"]

[[sections]]
name = "AI"
folder = "Newsletters/AI"
hours = 24
days = "weekday"

[[sections]]
name = "Longform"
folder = "Newsletters/Fintech"
hours = 72
days = ["sat", "sun"]

[feeds]
hours = 48
max_entries = 4
urls = ["https://harbor-daily.example/feed.xml"]

[[feeds.sources]]
url = "https://canopy-notes.example/feed.xml"
section = "AI"
max_entries = 2

[articles]
enabled = false

[edition]
facts = 5
max_cards = 2

[output]
path = "brief.html"
[figures]
show = []
"""
        config = load_config(self._write(text))
        self.assertFalse(config.mailbox.unread_only)
        self.assertEqual(("weekday",), config.sections[0].days)
        self.assertEqual(("sat", "sun"), config.sections[1].days)
        self.assertEqual("Newsletters/AI", config.sections[0].folder)
        self.assertEqual(2, len(config.feeds))
        self.assertEqual("AI", config.feeds[1].section)
        self.assertEqual(2, config.feeds[1].max_entries)
        self.assertEqual(5, config.fact_count)
        self.assertEqual(2, config.max_cards)
        with self.assertRaisesRegex(ConfigError, "https"):
            load_config(
                self._write(text.replace("https://harbor-daily.example/feed.xml", "http://harbor-daily.example/feed.xml"))
            )

    def _write(self, text: str) -> Path:
        import tempfile

        directory = tempfile.mkdtemp()
        path = Path(directory) / "config.toml"
        path.write_text(text, encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path


if __name__ == "__main__":
    unittest.main()
