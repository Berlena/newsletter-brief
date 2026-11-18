from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from newsletter_brief.cli import main
from newsletter_brief.config import load_config
from newsletter_brief.run import run_brief
from own_inbox_samples import (
    MODEL_NUMBER,
    SAMPLE_CONFIG,
    figure_bytes,
    sample_edition,
    write_sample_mail,
)

API_KEY = "test-api-key-value"
MAILBOX_SECRET = "test-mailbox-secret"
FROZEN = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz: object = None) -> datetime:
        return FROZEN


class FakeResponses:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.request: dict[str, object] | None = None

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.request = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.output_text))]
        )


def _install_openai(responses: FakeResponses) -> types.ModuleType:
    module = types.ModuleType("openai")

    class FakeOpenAI:
        def __init__(self, api_key: str, base_url: str | None = None) -> None:
            self.api_key = api_key
            self.base_url = base_url
            self.chat = SimpleNamespace(completions=responses)

    module.OpenAI = FakeOpenAI  # type: ignore[attr-defined]
    return module


class RunTests(unittest.TestCase):
    def test_end_to_end_with_five_letters_and_a_mocked_model(self) -> None:
        responses = FakeResponses(json.dumps(sample_edition()))
        records: list[str] = []
        handler = logging.Handler()
        handler.emit = lambda record: records.append(record.getMessage())  # type: ignore[method-assign]
        logger = logging.getLogger("newsletter_brief")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        stdout = io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                mail = root / "mail"
                write_sample_mail(mail)
                config_path = root / "config.toml"
                config_path.write_text(SAMPLE_CONFIG, encoding="utf-8")
                env = {
                    "LLM_API_KEY": API_KEY,
                    "LLM_MODEL": "mock-model",
                    "NEWSLETTER_BRIEF_MAILBOX_PASSWORD": MAILBOX_SECRET,
                }
                with (
                    patch.dict(os.environ, env, clear=False),
                    patch.dict("sys.modules", {"openai": _install_openai(responses)}),
                    patch("newsletter_brief.figures._http_get", side_effect=figure_bytes),
                    patch("newsletter_brief.run.datetime", FrozenDateTime),
                    redirect_stdout(stdout),
                ):
                    result = main(
                        ["run", "--config", str(config_path), "--eml-dir", str(mail), "--no-send"]
                    )
                html_path = root / "brief.html"
                self.assertEqual(0, result, stdout.getvalue())
                html = html_path.read_text(encoding="utf-8")
        finally:
            logger.removeHandler(handler)

        self.assertIn("Your Morning Brief", html)
        self.assertIn("Why this matters", html)
        self.assertIn("city services and climate", html)
        self.assertIn('id="figures"', html)
        self.assertIn("1.1000", html)
        self.assertIn("unavailable", html)
        self.assertIn("2,000", html)
        self.assertIn("Library budget vote", html)
        self.assertIn("Match at the small ground", html)
        self.assertIn('<details class="story-card">', html)
        self.assertIn("<summary>", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("Public demo", html)
        self.assertIn("Source check", html)
        self.assertIn("https://harbor-daily.example/library-vote", html)
        self.assertIn("https://quiet-shelf.example/three-novels", html)
        self.assertIn(MODEL_NUMBER, html)
        box = html[html.index('id="figures"') : html.index("</aside>", html.index('id="figures"'))]
        self.assertNotIn(MODEL_NUMBER, box)
        self.assertNotIn(API_KEY, html)
        self.assertNotIn(MAILBOX_SECRET, html)
        self.assertNotIn(API_KEY, "\n".join(records))
        self.assertNotIn(MAILBOX_SECRET, "\n".join(records))
        self.assertIsNotNone(responses.request)
        assert responses.request is not None
        self.assertFalse(responses.request["store"])
        self.assertIn("brief.html", stdout.getvalue())

    def test_invented_link_writes_nothing(self) -> None:
        payload = sample_edition()
        payload["events"][0]["source_url"] = "https://invented.example/no-such-letter"  # type: ignore[index]
        responses = FakeResponses(json.dumps(payload))
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mail = root / "mail"
            write_sample_mail(mail)
            config_path = root / "config.toml"
            config_path.write_text(SAMPLE_CONFIG, encoding="utf-8")
            env = {"LLM_API_KEY": API_KEY, "LLM_MODEL": "mock-model"}
            with (
                patch.dict(os.environ, env, clear=False),
                patch.dict("sys.modules", {"openai": _install_openai(responses)}),
                patch("newsletter_brief.figures._http_get", side_effect=figure_bytes),
                patch("newsletter_brief.run.datetime", FrozenDateTime),
                redirect_stderr(stderr),
            ):
                result = main(
                    ["run", "--config", str(config_path), "--eml-dir", str(mail), "--no-send"]
                )
            self.assertEqual(2, result)
            self.assertFalse((root / "brief.html").exists())
        self.assertIn("absent from the input feed", stderr.getvalue())
        self.assertIn("https://invented.example/no-such-letter", stderr.getvalue())
        self.assertNotIn(API_KEY, stderr.getvalue())

    def test_no_mail_does_not_call_the_model(self) -> None:
        called: list[str] = []

        def forbid_get(url: str) -> bytes:
            return figure_bytes(url)

        module = types.ModuleType("openai")

        class Boom:
            def __init__(self, api_key: str) -> None:
                called.append(api_key)

        module.OpenAI = Boom  # type: ignore[attr-defined]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "mail").mkdir()
            config_path = root / "config.toml"
            config_path.write_text(SAMPLE_CONFIG, encoding="utf-8")
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.dict("sys.modules", {"openai": module}),
                patch("newsletter_brief.figures._http_get", side_effect=forbid_get),
                patch("newsletter_brief.run.datetime", FrozenDateTime),
                redirect_stdout(io.StringIO()),
            ):
                result = main(
                    ["run", "--config", str(config_path), "--eml-dir", str(root / "mail"), "--no-send"]
                )
            html = (root / "brief.html").read_text(encoding="utf-8")
        self.assertEqual(0, result)
        self.assertEqual([], called)
        self.assertIn("No newsletters arrived", html)
        self.assertIn("unavailable", html)

    def test_mail_without_a_key_writes_nothing(self) -> None:
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mail = root / "mail"
            write_sample_mail(mail)
            config_path = root / "config.toml"
            config_path.write_text(SAMPLE_CONFIG, encoding="utf-8")
            with (
                patch.dict(os.environ, {"LLM_MODEL": "mock-model"}, clear=True),
                patch("newsletter_brief.figures._http_get", side_effect=figure_bytes),
                patch("newsletter_brief.run.datetime", FrozenDateTime),
                redirect_stderr(stderr),
            ):
                result = main(
                    ["run", "--config", str(config_path), "--eml-dir", str(mail), "--no-send"]
                )
            self.assertEqual(2, result)
            self.assertFalse((root / "brief.html").exists())
        self.assertIn("LLM_API_KEY", stderr.getvalue())

    def test_smtp_send_is_called_when_delivery_is_on(self) -> None:
        sent: list[str] = []

        class FakeSMTP:
            def __enter__(self) -> "FakeSMTP":
                return self

            def __exit__(self, *args: object) -> bool:
                return False

            debuglevel = 0

            def ehlo(self) -> None:
                return None

            def starttls(self) -> None:
                return None

            def login(self, user: str, password: str) -> None:
                sent.append(password)

            def send_message(self, message: object) -> None:
                sent.append("sent")

        responses = FakeResponses(json.dumps(sample_edition()))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mail = root / "mail"
            write_sample_mail(mail)
            config_path = root / "config.toml"
            text = SAMPLE_CONFIG.replace(
                "[delivery]\nenabled = false\n",
                "[delivery]\nenabled = true\n"
                'smtp_host = "smtp.example"\n'
                "smtp_port = 587\n"
                'to = "you@example.com"\n',
            )
            config_path.write_text(text, encoding="utf-8")
            config = load_config(config_path)
            self.assertTrue(config.delivery.enabled)
            env = {
                "LLM_API_KEY": API_KEY,
                "LLM_MODEL": "mock-model",
                "NEWSLETTER_BRIEF_MAILBOX_PASSWORD": MAILBOX_SECRET,
            }
            with (
                patch.dict(os.environ, env, clear=False),
                patch.dict("sys.modules", {"openai": _install_openai(responses)}),
                patch("newsletter_brief.figures._http_get", side_effect=figure_bytes),
                patch("newsletter_brief.run.datetime", FrozenDateTime),
            ):
                run_brief(
                    config,
                    eml_dir=mail,
                    send=True,
                    smtp_factory=lambda host, port: FakeSMTP(),
                )
        self.assertIn(MAILBOX_SECRET, sent)
        self.assertIn("sent", sent)

    def test_already_sent_skips_the_model(self) -> None:
        called: list[str] = []

        class Boom:
            def create(self, **kwargs: object) -> None:
                called.append("model")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mail = root / "mail"
            write_sample_mail(mail)
            config_path = root / "config.toml"
            text = SAMPLE_CONFIG.replace(
                "[delivery]\nenabled = false\n",
                "[delivery]\nenabled = true\n"
                'smtp_host = "smtp.example"\n'
                "smtp_port = 587\n"
                'to = "you@example.com"\n',
            )
            text += '\n[memory]\npath = "state.json"\ndays = 2\n'
            config_path.write_text(text, encoding="utf-8")
            (root / "state.json").write_text(
                '{"seen": [], "sent": ["2026-11-18"]}\n',
                encoding="utf-8",
            )
            config = load_config(config_path)
            with (
                patch("newsletter_brief.run.datetime", FrozenDateTime),
                self.assertRaises(Exception) as caught,
            ):
                try:
                    run_brief(
                        config,
                        eml_dir=mail,
                        send=True,
                        now=FROZEN,
                        client=SimpleNamespace(chat=SimpleNamespace(completions=Boom())),
                    )
                except Exception as exc:
                    self.assertIn("Already sent today", str(exc))
                    raise
        self.assertEqual([], called)
        self.assertIn("Already sent", str(caught.exception))

    def test_feed_items_reach_the_model_and_an_invented_link_is_refused(self) -> None:
        rss = (Path(__file__).parent / "fixtures" / "harbor-rss.xml").read_bytes()
        url = "https://harbor-daily.example/library-vote?id=3"
        story = {
            "title": "Library budget vote",
            "summary": "The council posted the agenda.",
            "why_it_matters": "The vote is the feed item.",
            "key_fact": "Thursday",
            "source_label": "Harbor Daily",
            "source_url": url,
            "reactions": "The letter calls it the week's main vote.",
            "context": "",
            "context_source": "",
        }
        good = {
            "title": "Brief",
            "edition": "Wednesday",
            "date": "2026-11-18",
            "read_time_minutes": 2,
            "opening_note": "One item.",
            "why_this_matters": "The library vote is the item.",
            "facts": ["Library budget vote is on Thursday"],
            "lead_story": story,
            "sections": [{"name": "City", "stories": [story]}],
            "events": [],
        }
        bad_story = dict(story, source_url="https://invented.example/not-in-the-feed")
        bad = dict(good, lead_story=bad_story, sections=[{"name": "City", "stories": [bad_story]}])
        env = {"LLM_API_KEY": API_KEY, "LLM_MODEL": "mock-model"}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mail = root / "mail"
            mail.mkdir()
            config_path = root / "config.toml"
            config_path.write_text(
                SAMPLE_CONFIG + '\n[feeds]\nurls = ["https://harbor-daily.example/feed.xml"]\nhours = 24\n',
                encoding="utf-8",
            )
            config = load_config(config_path)
            responses = FakeResponses(json.dumps(good))
            records: list[str] = []
            handler = logging.Handler()
            handler.emit = lambda record: records.append(record.getMessage())  # type: ignore[method-assign]
            logger = logging.getLogger("newsletter_brief")
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            try:
                with (
                    patch.dict(os.environ, env, clear=False),
                    patch("newsletter_brief.figures._http_get", side_effect=figure_bytes),
                    patch("newsletter_brief.run.datetime", FrozenDateTime),
                ):
                    run_brief(
                        config,
                        eml_dir=mail,
                        send=False,
                        now=FROZEN,
                        client=SimpleNamespace(chat=SimpleNamespace(completions=responses)),
                        feed_get=lambda feed_url: rss,
                    )
            finally:
                logger.removeHandler(handler)
            html = (root / "brief.html").read_text(encoding="utf-8")
            self.assertIn("Reactions", html)
            assert responses.request is not None
            payload = json.loads(responses.request["messages"][1]["content"])  # type: ignore[index]
            self.assertIn(url, [item["source_url"] for item in payload["items"]])
            self.assertTrue(any("items before prefilter:" in line for line in records))

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mail = root / "mail"
            mail.mkdir()
            config_path = root / "config.toml"
            config_path.write_text(
                SAMPLE_CONFIG + '\n[feeds]\nurls = ["https://harbor-daily.example/feed.xml"]\nhours = 24\n',
                encoding="utf-8",
            )
            config = load_config(config_path)
            responses_bad = FakeResponses(json.dumps(bad))
            with (
                patch.dict(os.environ, env, clear=False),
                patch("newsletter_brief.figures._http_get", side_effect=figure_bytes),
                patch("newsletter_brief.run.datetime", FrozenDateTime),
            ):
                with self.assertRaises(Exception) as caught:
                    run_brief(
                        config,
                        eml_dir=mail,
                        send=False,
                        now=FROZEN,
                        client=SimpleNamespace(chat=SimpleNamespace(completions=responses_bad)),
                        feed_get=lambda feed_url: rss,
                    )
            self.assertIn("absent from the input feed", str(caught.exception))
            self.assertFalse((root / "brief.html").exists())


if __name__ == "__main__":
    unittest.main()
