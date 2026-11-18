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
            self.assertIn("OPENAI_API_KEY, OPENAI_MODEL", stderr.getvalue())

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


if __name__ == "__main__":
    unittest.main()
