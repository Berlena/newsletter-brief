from __future__ import annotations

import re
import unittest
from dataclasses import replace
from pathlib import Path

from newsletter_brief.renderer import _CSS, render_html
from newsletter_brief.schema import load_brief

ROOT = Path(__file__).resolve().parents[1]


def css_color(variable: str) -> str:
    match = re.search(rf"--{re.escape(variable)}:\s*(#[0-9a-fA-F]{{6}});", _CSS)
    if match is None:
        raise AssertionError(f"CSS color variable --{variable} was not found")
    return match.group(1)


def relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (relative_luminance(first), relative_luminance(second)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


class RendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.brief = load_brief(ROOT / "demo" / "prepared_response.json")

    def test_render_is_deterministic(self) -> None:
        self.assertEqual(render_html(self.brief), render_html(self.brief))

    def test_text_and_attributes_are_escaped(self) -> None:
        hostile_lead = replace(
            self.brief.lead_story,
            title='<script>alert("title")</script>',
            source_label='Source "quoted" <unsafe>',
        )
        hostile = replace(
            self.brief,
            opening_note="<img src=x onerror=alert(1)>",
            lead_story=hostile_lead,
        )
        rendered = render_html(hostile)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img src=x", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("&lt;unsafe&gt;", rendered)

    def test_output_has_responsive_and_accessible_landmarks(self) -> None:
        rendered = render_html(self.brief)
        self.assertIn("@media (max-width: 760px)", rendered)
        self.assertIn('class="skip-link"', rendered)
        self.assertIn('aria-label="Demo architecture"', rendered)
        self.assertIn("Synthetic demo", rendered)

    def test_lead_palette_meets_wcag_aa(self) -> None:
        background = css_color("lead-bg")
        for foreground in ("lead-ink", "lead-secondary", "lead-hover"):
            with self.subTest(foreground=foreground):
                self.assertGreaterEqual(
                    contrast_ratio(background, css_color(foreground)),
                    4.5,
                )
        self.assertIn(".lead a:hover", _CSS)
        self.assertIn(".lead a:focus-visible", _CSS)
        self.assertLess(_CSS.index(".lead .source"), _CSS.index(".lead a:hover"))


if __name__ == "__main__":
    unittest.main()
