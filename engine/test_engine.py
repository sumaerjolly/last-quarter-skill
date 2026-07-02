"""Offline unit tests for the trust-critical logic. No network.

Run from the engine/ dir:  python3 -m unittest test_engine -v
"""
import unittest
from datetime import date

from lib import edgar, identity, news, window
from last_quarter import build_footer


class TestNewsCommonWordFilter(unittest.TestCase):
    """#1: the ordinary-word filter must NOT delete funding/event headlines."""

    def setUp(self):
        self.bad = news._common_word_usage("Increase")

    def test_funding_headline_survives(self):
        # was silently dropped by a nameless [%$]\d alternative — the #1 ABM trigger
        self.assertIsNone(self.bad.search("Increase raises $25M Series B led by Foo"))
        self.assertTrue(news._EVENT.search("Increase raises $25M Series B led by Foo"))

    def test_ordinary_money_usage_dropped(self):
        self.assertIsNotNone(self.bad.search("State approves $70M increase for AES"))

    def test_ordinary_noun_usage_dropped(self):
        self.assertIsNotNone(self.bad.search("Eating fruit may increase risk of cancer"))

    def test_event_filter_needs_a_verb(self):
        self.assertIsNone(news._EVENT.search("Golden Gate Bridge toll increase Wednesday"))


class TestEdgarMatching(unittest.TestCase):
    """#2: normalized-exact name match — no wrong-entity public routing."""

    def setUp(self):
        edgar._TICKERS_CACHE["ok"] = True
        edgar._TICKERS_CACHE["data"] = {
            "0": {"cik_str": 1561550, "ticker": "DDOG", "title": "Datadog, Inc."},
            "1": {"cik_str": 1, "ticker": "MRCY", "title": "Mercury Systems Inc"},
            "2": {"cik_str": 2, "ticker": "RAMP", "title": "LiveRamp Holdings, Inc."},
            "3": {"cik_str": 3, "ticker": "WAVE", "title": "Wave Life Sciences Ltd."},
        }

    def tearDown(self):
        edgar._TICKERS_CACHE["ok"] = None
        edgar._TICKERS_CACHE["data"] = None

    def test_real_match(self):
        self.assertEqual(edgar.lookup_cik("Datadog")["ticker"], "DDOG")

    def test_mercury_does_not_match_defense_contractor(self):
        self.assertIsNone(edgar.lookup_cik("Mercury"))  # != "Mercury Systems"

    def test_ticker_collision_rejected(self):
        self.assertIsNone(edgar.lookup_cik("Ramp"))  # ticker RAMP is LiveRamp

    def test_wave_not_life_sciences(self):
        self.assertIsNone(edgar.lookup_cik("Wave"))


class TestIdentity(unittest.TestCase):
    def test_registrable_domain(self):
        self.assertEqual(identity.registrable_domain("https://www.airops.com/blog"), "airops.com")
        self.assertEqual(identity.registrable_domain("docs.increase.com"), "increase.com")
        self.assertEqual(identity.registrable_domain("https://mercury.com"), "mercury.com")

    def test_brand_slug(self):
        self.assertEqual(identity.brand_slug("increase.com"), "increase")

    def test_norm_company_strips_only_legal_suffixes(self):
        self.assertEqual(identity.norm_company("Datadog, Inc."), "datadog")
        self.assertEqual(identity.norm_company("Mercury Systems Inc"), "mercury systems")
        self.assertEqual(identity.norm_company("Wave Life Sciences Ltd."), "wave life sciences")


class TestWindow(unittest.TestCase):
    def setUp(self):
        self.w = window.make_window(date(2026, 7, 1))

    def test_buckets(self):
        self.assertEqual(window.bucket("2026-05-01", self.w), "in_window")
        self.assertEqual(window.bucket("2026-02-15", self.w), "prior")
        self.assertEqual(window.bucket("2025-01-01", self.w), "out")
        self.assertEqual(window.bucket("not a date", self.w), "unknown")

    def test_date_formats(self):
        self.assertEqual(window.bucket("Wed, 13 May 2026 12:00:00 GMT", self.w), "in_window")  # RFC822
        self.assertEqual(window.bucket("2026-05-13T18:37:03.872+00:00", self.w), "in_window")  # ISO
        self.assertIsNotNone(window.parse_dt(1747000000000))  # epoch ms (Lever)


class TestFooter(unittest.TestCase):
    """#10: skipped/not-run excluded from denominator; error≠empty."""

    def test_footer_accounting(self):
        report = {"sources": {
            "careers": {"status": "active", "posted_in_window": 9},
            "news": {"status": "error"},
            "blog": {"status": "empty"},
            "edgar": {"status": "skipped"},
            # github intentionally absent (e.g. --no-github)
        }}
        f = build_footer(report)
        self.assertIn("careers ✓ 9", f)
        self.assertIn("news ⚠", f)
        self.assertIn("blog ✗", f)
        self.assertIn("edgar —", f)
        self.assertIn("github —", f)
        self.assertIn("1/3 applicable", f)  # skipped + missing excluded from denominator


if __name__ == "__main__":
    unittest.main()
