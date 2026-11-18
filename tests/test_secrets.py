from __future__ import annotations

import logging
import subprocess
import unittest
from unittest.mock import patch

from newsletter_brief.secrets import (
    MAILBOX_ACCOUNT,
    MAILBOX_ENV,
    SecretError,
    read_secret,
    redact,
    require_secret,
)


class SecretsTests(unittest.TestCase):
    def test_environment_wins_over_the_keychain(self) -> None:
        def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
            raise AssertionError(argv)

        with patch.dict("os.environ", {MAILBOX_ENV: "from-the-environment"}, clear=False):
            value = read_secret(MAILBOX_ENV, MAILBOX_ACCOUNT, runner=runner)
        self.assertEqual("from-the-environment", value)

    def test_keychain_is_used_when_the_environment_is_empty(self) -> None:
        seen: list[list[str]] = []

        def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="from-the-keychain\n", stderr="no")

        with patch.dict("os.environ", {MAILBOX_ENV: ""}, clear=False), patch(
            "newsletter_brief.secrets.sys.platform", "darwin"
        ):
            value = read_secret(MAILBOX_ENV, MAILBOX_ACCOUNT, runner=runner)
        self.assertEqual("from-the-keychain", value)
        self.assertEqual("security", seen[0][0])
        self.assertIn(MAILBOX_ACCOUNT, seen[0])
        self.assertNotIn("from-the-keychain", " ".join(seen[0]))

    def test_failed_keychain_lookup_is_a_missing_secret(self) -> None:
        def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                argv, 1, stdout="should-not-be-used", stderr="not found"
            )

        with patch.dict("os.environ", {}, clear=True), patch(
            "newsletter_brief.secrets.sys.platform", "darwin"
        ):
            with self.assertRaises(SecretError) as caught:
                require_secret(MAILBOX_ENV, MAILBOX_ACCOUNT, runner=runner)
        self.assertNotIn("should-not-be-used", str(caught.exception))
        self.assertIn(MAILBOX_ENV, str(caught.exception))

    def test_redact_replaces_known_secrets(self) -> None:
        secret = "mailbox-secret-value"
        self.assertEqual(
            "login failed for [redacted]",
            redact(f"login failed for {secret}", [secret, ""]),
        )

    def test_redacted_text_can_be_logged(self) -> None:
        secret = "mailbox-secret-value"
        records: list[str] = []
        handler = logging.Handler()
        handler.emit = lambda record: records.append(record.getMessage())  # type: ignore[method-assign]
        logger = logging.getLogger("newsletter_brief.test_secrets")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            logger.info(redact(f"could not log in with {secret}", [secret]))
        finally:
            logger.removeHandler(handler)
        self.assertEqual(["could not log in with [redacted]"], records)
        self.assertNotIn(secret, records[0])


if __name__ == "__main__":
    unittest.main()
