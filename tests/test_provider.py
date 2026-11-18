from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from newsletter_brief.config import ConfigError, load_config
from newsletter_brief.inputs import load_feed
from newsletter_brief.provider import (
    DEFAULT_BASE_URL,
    ProviderError,
    is_local_base,
    resolve_provider,
)
from newsletter_brief.schema import BRIEF_JSON_SCHEMA
from newsletter_brief.synthesis import SynthesisError, live_synthesis

ROOT = Path(__file__).resolve().parents[1]


class RecordingCompletions:
    def __init__(self, content: str, *, fail_schema: bool = False, invalid_on_json: str | None = None) -> None:
        self.content = content
        self.fail_schema = fail_schema
        self.invalid_on_json = invalid_on_json
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        response_format = kwargs.get("response_format")
        kind = response_format.get("type") if isinstance(response_format, dict) else None
        if self.fail_schema and kind == "json_schema":
            raise RuntimeError("response_format json_schema is not supported")
        content = self.invalid_on_json if kind == "json_object" and self.invalid_on_json is not None else self.content
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


def _client(completions: RecordingCompletions) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def _no_keychain(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")


class ProviderConfigTests(unittest.TestCase):
    def test_defaults_to_openai_and_reads_the_new_names(self) -> None:
        env = {"LLM_API_KEY": "provider-key", "LLM_MODEL": "demo-model"}
        with patch.dict("os.environ", env, clear=True):
            settings = resolve_provider()
        self.assertEqual(DEFAULT_BASE_URL, settings.base_url)
        self.assertEqual("demo-model", settings.model)
        self.assertEqual("provider-key", settings.api_key)
        self.assertTrue(settings.sends_openai_flags)

    def test_environment_overrides_the_config_file(self) -> None:
        env = {
            "LLM_BASE_URL": "https://api.mistral.ai/v1",
            "LLM_MODEL": "from-env",
            "LLM_API_KEY": "provider-key",
        }
        with patch.dict("os.environ", env, clear=True):
            settings = resolve_provider(
                config_base_url="https://api.openai.com/v1",
                config_model="from-file",
            )
        self.assertEqual("https://api.mistral.ai/v1", settings.base_url)
        self.assertEqual("from-env", settings.model)
        self.assertFalse(settings.sends_openai_flags)

    def test_config_model_is_used_when_the_environment_is_empty(self) -> None:
        with patch.dict("os.environ", {"LLM_API_KEY": "provider-key"}, clear=True):
            settings = resolve_provider(config_model="from-file")
        self.assertEqual("from-file", settings.model)
        self.assertEqual(DEFAULT_BASE_URL, settings.base_url)

    def test_legacy_openai_names_still_work(self) -> None:
        env = {"OPENAI_API_KEY": "legacy-key", "OPENAI_MODEL": "legacy-model"}
        with patch.dict("os.environ", env, clear=True):
            settings = resolve_provider()
        self.assertEqual("legacy-key", settings.api_key)
        self.assertEqual("legacy-model", settings.model)

    def test_a_local_model_does_not_need_a_key(self) -> None:
        env = {"LLM_BASE_URL": "http://127.0.0.1:11434/v1", "LLM_MODEL": "local-model"}
        with patch.dict("os.environ", env, clear=True):
            settings = resolve_provider(runner=_no_keychain)
        self.assertTrue(is_local_base(settings.base_url))
        self.assertIsNone(settings.api_key)
        self.assertEqual("local", settings.client_key())
        self.assertFalse(settings.sends_openai_flags)

    def test_a_remote_provider_without_a_key_is_rejected(self) -> None:
        env = {"LLM_BASE_URL": "https://api.mistral.ai/v1", "LLM_MODEL": "some-model"}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(ProviderError) as caught:
                resolve_provider(runner=_no_keychain)
        self.assertIn("LLM_API_KEY", str(caught.exception))
        self.assertNotIn("some-model-secret", str(caught.exception))

    def test_config_file_rejects_an_api_key(self) -> None:
        text = """
[mailbox]
host = "imap.example"
user = "you@example.com"
[senders]
allow = ["news.example"]
[output]
path = "brief.html"
[figures]
show = []
[llm]
base_url = "https://api.mistral.ai/v1"
model = "some-model"
api_key = "do-not-put-this-here"
"""
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "not allowed in the config file"):
                load_config(path)

    def test_example_config_has_no_key_and_optional_base_url(self) -> None:
        config = load_config(ROOT / "config.example.toml")
        self.assertEqual("https://api.openai.com/v1", config.llm_base_url)
        self.assertIsNone(config.llm_model)


class JsonFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.feed = load_feed(ROOT / "demo" / "newsletters.json")
        self.raw = json.loads((ROOT / "demo" / "prepared_response.json").read_text())

    def test_openai_request_uses_strict_schema_and_store_false(self) -> None:
        completions = RecordingCompletions(json.dumps(self.raw))
        live_synthesis(
            self.feed,
            api_key="provider-key",
            model="demo-model",
            base_url=DEFAULT_BASE_URL,
            client=_client(completions),
        )
        self.assertEqual(1, len(completions.calls))
        call = completions.calls[0]
        self.assertEqual(False, call["store"])
        self.assertEqual("json_schema", call["response_format"]["type"])  # type: ignore[index]
        self.assertEqual(BRIEF_JSON_SCHEMA, call["response_format"]["json_schema"]["schema"])  # type: ignore[index]
        self.assertNotIn("provider-key", json.dumps(call))

    def test_other_providers_do_not_receive_openai_flags(self) -> None:
        completions = RecordingCompletions(json.dumps(self.raw))
        live_synthesis(
            self.feed,
            api_key="provider-key",
            model="demo-model",
            base_url="https://api.mistral.ai/v1",
            client=_client(completions),
        )
        self.assertNotIn("store", completions.calls[0])
        self.assertEqual("json_schema", completions.calls[0]["response_format"]["type"])  # type: ignore[index]

    def test_json_mode_fallback_is_validated_locally(self) -> None:
        fenced = "```json\n" + json.dumps(self.raw) + "\n```"
        completions = RecordingCompletions(fenced, fail_schema=True)
        brief = live_synthesis(
            self.feed,
            api_key="provider-key",
            model="local-model",
            base_url="http://localhost:11434/v1",
            client=_client(completions),
        )
        self.assertEqual("Your Morning Brief", brief.title)
        self.assertEqual(
            ["json_schema", "json_object"],
            [call["response_format"]["type"] for call in completions.calls],  # type: ignore[index]
        )
        self.assertNotIn("store", completions.calls[0])
        self.assertNotIn("store", completions.calls[1])

    def test_invalid_json_mode_output_fails_loudly(self) -> None:
        completions = RecordingCompletions("not-json", fail_schema=True, invalid_on_json="still not json")
        with self.assertRaisesRegex(SynthesisError, "not valid JSON"):
            live_synthesis(
                self.feed,
                api_key="",
                model="local-model",
                base_url="http://localhost:11434/v1",
                client=_client(completions),
            )
        self.assertEqual(4, len(completions.calls))

    def test_schema_invalid_json_fails_loudly(self) -> None:
        completions = RecordingCompletions('{"title":"only"}', fail_schema=True, invalid_on_json='{"title":"only"}')
        with self.assertRaisesRegex(SynthesisError, "no brief was written"):
            live_synthesis(
                self.feed,
                api_key="",
                model="local-model",
                base_url="http://127.0.0.1:1234/v1",
                client=_client(completions),
            )

    def test_an_ordinary_api_error_does_not_fall_back(self) -> None:
        class Boom:
            def __init__(self) -> None:
                self.calls = 0

            def create(self, **kwargs: object) -> None:
                self.calls += 1
                raise RuntimeError("invalid api key provider-key")

        boom = Boom()
        with self.assertRaises(SynthesisError) as caught:
            live_synthesis(
                self.feed,
                api_key="provider-key",
                model="demo-model",
                base_url="https://api.mistral.ai/v1",
                client=_client(boom),  # type: ignore[arg-type]
            )
        self.assertEqual(1, boom.calls)
        self.assertNotIn("provider-key", str(caught.exception))
        self.assertIn("[redacted]", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
