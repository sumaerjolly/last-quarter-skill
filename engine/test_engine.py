"""Offline unit tests for the trust-critical logic. No network.

Run from the engine/ dir:  python3 -m unittest test_engine -v
"""
import unittest
from datetime import date

from lib import careers, customer_wins, edgar, github, identity, jd_mining, news, window
from last_quarter import build_footer


class TestGeoRollup(unittest.TestCase):
    def test_emea_flagged(self):
        jw = [{"location": "London"}, {"location": "Berlin"}, {"location": "New York"}]
        rollup, note = careers._geo_rollup(jw)
        self.assertEqual(dict(rollup).get("EMEA"), 2)
        self.assertIn("EMEA", note or "")

    def test_remote_emea_buckets_emea(self):
        self.assertEqual(careers._classify_location("Remote - EMEA"), "EMEA")
        self.assertEqual(careers._classify_location("Remote"), "Remote")

    def test_all_us_no_note(self):
        jw = [{"location": "New York"}, {"location": "San Francisco"}, {"location": "Austin"}]
        _, note = careers._geo_rollup(jw)
        self.assertIsNone(note)


class TestSeniorRoles(unittest.TestCase):
    def _t(self, titles):
        return {r["title"] for r in careers._senior_roles(
            [{"title": t, "date": "2026-05-01"} for t in titles])}

    def test_flagged(self):
        self.assertEqual(
            self._t(["VP of Engineering", "Head of Sales", "Founding Biz Ops Lead", "Director, Product"]),
            {"VP of Engineering", "Head of Sales", "Founding Biz Ops Lead", "Director, Product"})

    def test_ic_not_flagged(self):
        self.assertEqual(self._t(["Sales Development Representative", "Senior Software Engineer"]), set())


class TestNewRepos(unittest.TestCase):
    def setUp(self):
        self.w = window.make_window(date(2026, 7, 6))

    def test_in_window_included(self):
        repos = [{"name": "increase-csharp", "created_at": "2026-05-01T00:00:00Z", "fork": False}]
        self.assertEqual([r["name"] for r in github._new_repos(repos, self.w)], ["increase-csharp"])

    def test_fork_excluded(self):
        repos = [{"name": "x", "created_at": "2026-05-01T00:00:00Z", "fork": True}]
        self.assertEqual(github._new_repos(repos, self.w), [])

    def test_old_repo_excluded(self):
        repos = [{"name": "x", "created_at": "2025-01-01T00:00:00Z", "fork": False}]
        self.assertEqual(github._new_repos(repos, self.w), [])


class TestCustomerWins(unittest.TestCase):
    def _c(self, title, brand=None):
        return [x["customer"] for x in
                customer_wins.extract_customer_wins([{"title": title, "url": "u"}], brand=brand)]

    def test_angi(self):
        self.assertEqual(self._c("How Angi Built a Longtail Content Strategy that Converts 79% Better"), ["Angi"])

    def test_lowercase_to_rejected(self):  # real AirOps title that must NOT false-positive
        self.assertEqual(self._c("How to Build a Brand Kit That Makes Your Content Sound Like You"), [])

    def test_stoplist_rejected(self):
        self.assertEqual(self._c("How AI Scaled Its Content Platform"), [])

    def test_self_name_rejected(self):
        self.assertEqual(self._c("Ramp Customer Story", brand="Ramp"), [])

    def test_case_study(self):
        self.assertEqual(self._c("Case Study: Kayak"), ["Kayak"])


def _stack(text, brand=None):
    return {t["tool"] for t in jd_mining.mine([{"title": "Eng", "url": "u", "text": text}],
                                              brand=brand)["tech_stack"]}


class TestJdMining(unittest.TestCase):
    """Precision is the point — ambiguous tokens only count in skill context."""

    def test_real_stack_extracted(self):
        s = _stack("Requirements: strong experience with Salesforce, Snowflake and dbt.")
        self.assertEqual(s, {"Salesforce", "Snowflake", "dbt"})

    def test_ordinary_word_not_a_tool(self):
        # 'customer outreach' / 'audience segment' must NOT become Outreach / Segment
        self.assertNotIn("Outreach", _stack("Own customer outreach and audience segments."))
        self.assertNotIn("Segment", _stack("Own customer outreach and audience segments."))

    def test_ambiguous_with_cue_counts(self):
        self.assertIn("Gong", _stack("Proficiency in Gong and Outreach is required."))
        self.assertIn("Outreach", _stack("Proficiency in Gong and Outreach is required."))

    def test_go_to_market_is_not_go_language(self):
        self.assertNotIn("Go", _stack("Experience with go-to-market strategy and a go-getter attitude."))

    def test_go_language_detected_in_context(self):
        self.assertIn("Go", _stack("Backend services written in Go and Rust."))

    def test_company_own_name_excluded(self):
        self.assertNotIn("Notion", _stack("You'll use Notion daily.", brand="Notion"))

    def test_priorities_extracted(self):
        p = jd_mining.mine([{"title": "AE", "url": "u",
                             "text": "You'll lead our EU expansion into new markets."}])["priorities"]
        self.assertTrue(any("EU expansion" in x["text"] for x in p))
        self.assertEqual(p[0]["job"], "AE")

    def _inits(self, text):
        return [x["text"] for x in
                jd_mining.mine([{"title": "X", "url": "u", "text": text}])["initiatives"]]

    def test_initiatives_detected(self):
        self.assertTrue(self._inits("We are building a brand new Applied AI team."))
        self.assertTrue(self._inits("You'll be the first hire on our newly formed EU team."))
        self.assertTrue(self._inits("Help us stand up a new RevOps function."))
        self.assertTrue(self._inits("This is a greenfield, 0-to-1 opportunity."))

    def test_new_customers_is_not_an_initiative(self):
        self.assertFalse(self._inits("We love our new customers and want to grow the account."))


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
