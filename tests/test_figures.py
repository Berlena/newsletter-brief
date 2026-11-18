from __future__ import annotations

import re
import unittest
from datetime import date
from unittest.mock import patch

from newsletter_brief.figures import (
    COINGECKO_URL,
    ECB_DAILY_URL,
    fetch_figures,
    parse_coingecko,
    parse_ecb_daily,
)
from newsletter_brief.models import Brief, Figure, Section, Story
from newsletter_brief.renderer import render_html
from own_inbox_samples import COIN_JSON, ECB_XML, MODEL_NUMBER, figure_bytes


def _edition(**overrides: object) -> Brief:
    lead = Story(
        title="Library vote",
        summary=f"The model wrote {MODEL_NUMBER} in this sentence.",
        why_it_matters="It decides what stays open.",
        key_fact="Thursday",
        source_label="Harbor Daily",
        source_url="https://harbor-daily.example/library-vote",
    )
    brief = Brief(
        synthetic=False,
        title="Your Morning Brief",
        edition="Wednesday brief",
        edition_date=date(2026, 11, 18),
        read_time_minutes=4,
        opening_note="A quiet morning.",
        why_this_matters="The vote is the item that matches your list.",
        top_lines=("Library vote", "River gauge", "Match moved"),
        lead_story=lead,
        sections=(Section(name="City", stories=(lead,)),),
        public_demo=False,
    )
    if overrides:
        from dataclasses import replace

        brief = replace(brief, **overrides)  # type: ignore[arg-type]
    return brief


class FigureParseTests(unittest.TestCase):
    def test_ecb_rates_keep_the_published_text_and_date(self) -> None:
        parsed = parse_ecb_daily(ECB_XML)
        self.assertEqual("2026-11-17", parsed.day)
        self.assertEqual("1.1000", parsed.rates["USD"])
        self.assertEqual("0.8500", parsed.rates["GBP"])

    def test_coingecko_keeps_a_missing_coin_out(self) -> None:
        parsed = parse_coingecko(COIN_JSON)
        self.assertNotIn("btc-usd", parsed)
        value, as_of = parsed["eth-usd"]
        self.assertEqual("2,000", value)
        self.assertIn("UTC", as_of)

    def test_failed_fetch_is_unavailable_and_has_no_number(self) -> None:
        def get(url: str) -> bytes:
            raise OSError(f"down {url}")

        figures = fetch_figures(("eur-usd", "btc-usd"), get=get)
        self.assertEqual(("eur-usd", "btc-usd"), tuple(item.figure_id for item in figures))
        for figure in figures:
            self.assertFalse(figure.available)
            self.assertEqual("unavailable", figure.value)
            self.assertEqual("", figure.as_of)
            self.assertNotRegex(figure.value, r"\d")

    def test_one_source_can_fail_while_the_other_is_kept(self) -> None:
        def get(url: str) -> bytes:
            if url == ECB_DAILY_URL:
                return ECB_XML
            raise OSError("coin down")

        figures = fetch_figures(("eur-usd", "eth-usd"), get=get)
        self.assertEqual("1.1000", figures[0].value)
        self.assertEqual("ECB reference rate", figures[0].source_name)
        self.assertEqual("2026-11-17", figures[0].as_of)
        self.assertEqual("unavailable", figures[1].value)
        self.assertNotIn(COINGECKO_URL, figures[0].value)

    def test_garbage_payload_is_unavailable(self) -> None:
        figures = fetch_figures(("eur-gbp", "btc-usd"), get=lambda url: b"not data")
        self.assertEqual(["unavailable", "unavailable"], [figure.value for figure in figures])

    def test_default_fetch_goes_to_the_http_helper(self) -> None:
        with patch("newsletter_brief.figures._http_get", side_effect=OSError("no network")) as http:
            figures = fetch_figures(("eur-usd",))
        http.assert_called_once_with(ECB_DAILY_URL)
        self.assertEqual("unavailable", figures[0].value)

    def test_sample_bytes_match_the_real_parser(self) -> None:
        figures = fetch_figures(
            ("eur-usd", "eur-gbp", "btc-usd", "eth-usd"),
            get=figure_bytes,
        )
        self.assertEqual(
            ["1.1000", "0.8500", "unavailable", "2,000"],
            [figure.value for figure in figures],
        )


class FigureBoxTests(unittest.TestCase):
    def test_model_numbers_do_not_enter_the_figures_box(self) -> None:
        figures = fetch_figures(
            ("eur-usd", "eur-gbp", "btc-usd", "eth-usd"),
            get=figure_bytes,
        )
        html = render_html(_edition(figures=figures))
        self.assertIn(MODEL_NUMBER, html)
        start = html.index('id="figures"')
        box = html[start : html.index("</aside>", start)]
        self.assertIn("1.1000", box)
        self.assertIn("0.8500", box)
        self.assertIn("2,000", box)
        self.assertIn("unavailable", box)
        self.assertIn("ECB reference rate", box)
        self.assertIn("2026-11-17", box)
        self.assertIn("CoinGecko", box)
        self.assertNotIn(MODEL_NUMBER, box)
        self.assertIn("Not written by the summary.", box)

    def test_failed_box_says_unavailable_and_has_no_digits(self) -> None:
        figures = (
            Figure(
                figure_id="eur-usd",
                label="EUR to USD",
                value="unavailable",
                source_name="ECB reference rate",
                source_url="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
                as_of="",
                available=False,
            ),
        )
        html = render_html(_edition(figures=figures, opening_note=f"Model number {MODEL_NUMBER}"))
        start = html.index('id="figures"')
        box = html[start : html.index("</aside>", start)]
        values = re.findall(r'class="figure-value">(.*?)</p>', box)
        self.assertEqual(["unavailable"], values)
        for value in values:
            self.assertNotRegex(value, r"\d")
        self.assertIn("not fetched", box)
        self.assertNotIn(MODEL_NUMBER, box)
        self.assertNotRegex(box, r"20\d\d")


if __name__ == "__main__":
    unittest.main()
