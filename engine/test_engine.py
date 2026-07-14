"""Offline unit tests for the trust-critical logic. No network.

Run from the engine/ dir:  python3 -m unittest test_engine -v
"""
import unittest
from datetime import date

from lib import careers, competitive, customer_wins, edgar, exa, github, identity, jd_mining, news, window
from lib.signals import build_signals
from last_quarter import build_footer


class TestPDL(unittest.TestCase):
    def test_senior_detection(self):
        from lib.pdl import _is_senior
        self.assertTrue(_is_senior({"vp"}, "VP Sales"))
        self.assertTrue(_is_senior(set(), "Head of People"))
        self.assertTrue(_is_senior({"director"}, "Director, Product"))
        self.assertFalse(_is_senior({"senior"}, "Senior Software Engineer"))  # IC, not senior
        self.assertFalse(_is_senior(set(), "Account Executive"))

    def test_unavailable_without_key(self):
        import os
        from lib import pdl
        old = os.environ.pop("PDL_API_KEY", None)
        try:
            self.assertFalse(pdl.available())
        finally:
            if old:
                os.environ["PDL_API_KEY"] = old


class TestConfig(unittest.TestCase):
    def test_parse_env_file(self):
        import pathlib
        import tempfile
        from lib import config
        p = pathlib.Path(tempfile.mktemp(suffix=".env"))
        p.write_text("# comment\nA_KEY=xyz\nQ_EMPTY=\nB_KEY='quoted'\nbad line\n")
        d = config._parse(p)
        self.assertEqual(d["A_KEY"], "xyz")
        self.assertEqual(d["B_KEY"], "quoted")   # quotes stripped
        self.assertEqual(d["Q_EMPTY"], "")       # empty parsed; load_env skips empties
        self.assertNotIn("bad line", d)


class TestFirecrawl(unittest.TestCase):
    def test_unavailable_without_key(self):
        import os
        from lib import firecrawl_render
        old = os.environ.pop("FIRECRAWL_API_KEY", None)
        try:
            self.assertFalse(firecrawl_render.available())
        finally:
            if old:
                os.environ["FIRECRAWL_API_KEY"] = old

    def test_post_url_pattern(self):
        from lib.firecrawl_render import _POST
        self.assertTrue(_POST.search("https://x.com/resources/some-guide-here"))
        self.assertTrue(_POST.search("https://x.com/blog/my-post"))
        self.assertIsNone(_POST.search("https://x.com/pricing"))


class TestExaClassify(unittest.TestCase):
    """Entity classification for Exa results (the common-word collision guard)."""

    def test_same_name_company_domain_is_collision(self):
        # reflowmedical.com is a DIFFERENT company that happens to contain "reflow"
        self.assertEqual(exa.classify_result(
            "https://reflowmedical.com/pr", "Reflow Medical Announces Trial", "", "Reflow", "reflow.ai"),
            "collision")

    def test_neutral_outlet_naming_company_is_kept(self):
        self.assertEqual(exa.classify_result(
            "https://pitchbook.com/x", "Reflow.ai 2026 Company Profile", "", "Reflow", "reflow.ai"),
            "keep")

    def test_own_domain_always_kept(self):
        self.assertEqual(exa.classify_result(
            "https://reflow.ai/blog/x", "Anything", "", "Reflow", "reflow.ai"), "keep")

    def test_unrelated_result_dropped(self):
        self.assertEqual(exa.classify_result(
            "https://techcrunch.com/x", "Convey closes $38M round", "automation startup", "Reflow", "reflow.ai"),
            "drop")


class TestCompetitive(unittest.TestCase):
    def _x(self, title, brand):
        return competitive.extract_competitive([{"title": title, "url": "u", "source": "blog"}], brand)

    def test_displacement_win(self):
        r = self._x("Why Childcare Programs Switch from Playground to Brightwheel", "Brightwheel")
        self.assertEqual((r[0]["competitor"], r[0]["kind"]), ("Playground", "displacement_win"))

    def test_competitor_attack(self):
        r = self._x("Rippling launches Vanta/Delve competitor", "Vanta")
        self.assertEqual((r[0]["competitor"], r[0]["kind"]), ("Rippling", "competitor_attack"))

    def test_comparison(self):
        r = self._x("Brightwheel vs Procare: which is better", "Brightwheel")
        self.assertEqual((r[0]["competitor"], r[0]["kind"]), ("Procare", "comparison"))

    def test_no_false_positive(self):
        self.assertEqual(self._x("How Brightwheel Built a Longtail Content Strategy", "Brightwheel"), [])
        self.assertEqual(self._x("Why teams switch to Brightwheel", "Brightwheel"), [])  # no named competitor


class TestSignals(unittest.TestCase):
    def _report(self):
        return {"sources": {
            "careers": {"status": "active", "ats": "ashby", "board_url": "b",
                        "listed_total": 23, "posted_in_window": 9,
                        "dept_concentration": [["Sales", 4]],
                        "senior_roles": [{"title": "VP Sales", "date": "2026-05-26", "url": "u1"}],
                        "geo_note": "2 of 9 EMEA-based — possible EMEA expansion.",
                        "initiatives": [{"text": "stand up new X", "job": "EM", "url": "u2"}],
                        "priorities": [{"text": "lead EU", "job": "AE", "url": "u3"}],
                        "tech_by_category": {"Languages": ["Python", "Go"]}},
            "news": {"status": "active", "noisy": True,
                     "signals": [{"title": "X raises $10M", "outlet": "TechCrunch",
                                  "date": "2026-05-01", "url": "n1"}]},
            "status": {"status": "active",
                       "signals": [{"title": "API outage", "date": "2026-05-10", "url": "s1"}]},
        }}

    def test_shape_and_categories(self):
        sig = build_signals(self._report())
        for r in sig:  # every record has exactly the uniform key set (+ score)
            self.assertEqual(set(r),
                             {"type", "category", "claim", "date", "url", "source", "confidence", "score"})
        cats = {r["category"] for r in sig}
        self.assertTrue({"hiring", "leadership", "expansion", "strategy", "tech", "news", "risk"} <= cats)

    def _win(self):
        return {"window": {"end": "2026-07-07", "start": "2026-04-08"}, "sources": {}}

    def test_new_hire_outranks_fresh_blog_post(self):
        rep = self._win()
        rep["sources"] = {
            "pdl": {"status": "active", "dept_rollup": [], "senior_hires": [
                {"name": "Jane Doe", "title": "VP Eng", "start": "2026-05-28", "linkedin": "u"}]},
            "blog": {"status": "active", "signals": [
                {"title": "A blog post", "date": "2026-07-05", "url": "b"}]},
        }
        sig = build_signals(rep)
        hire = next(r for r in sig if r["type"] == "new_hire")
        post = next(r for r in sig if r["type"] == "blog_post")
        self.assertGreater(hire["score"], post["score"])
        self.assertLess(sig.index(hire), sig.index(post))

    def test_low_confidence_news_below_primary_weight4(self):
        rep = self._win()
        rep["sources"] = {
            "news": {"status": "active", "noisy": True, "signals": [
                {"title": "Something happened", "outlet": "X", "date": "2026-07-06", "url": "n"}]},
            "status": {"status": "active", "signals": [
                {"title": "Outage", "date": "2026-05-01", "url": "s"}]},
        }
        sig = build_signals(rep)
        news = next(r for r in sig if r["type"] == "news")
        inc = next(r for r in sig if r["type"] == "incident")
        self.assertLess(news["score"], inc["score"])

    def test_funding_verb_news_boosted(self):
        from lib import signals
        rep = self._win()
        rep["sources"] = {"news": {"status": "active", "signals": [
            {"title": "Acme raises $25M Series B", "outlet": "TC", "date": "2026-05-01", "url": "a"},
            {"title": "Acme opens new office", "outlet": "TC", "date": "2026-05-01", "url": "b"}]}}
        sig = build_signals(rep)
        boosted = next(r for r in sig if "raises" in r["claim"])
        plain = next(r for r in sig if "opens" in r["claim"])
        self.assertGreater(boosted["score"], plain["score"])

    def test_collision_propagation_downgrades_news(self):
        rep = self._win()
        rep["sources"] = {
            "exa": {"status": "active", "noisy": True, "collisions": ["reflowmedical.com"], "signals": []},
            "news": {"status": "active", "signals": [
                {"title": "Someone raises $50M", "outlet": "TC", "date": "2026-07-01", "url": "n"}]},
            "careers": {"status": "active", "ats": "ashby", "board_url": "b", "listed_total": 5,
                        "posted_in_window": 3, "dept_concentration": [],
                        "senior_roles": [{"title": "VP Eng", "date": "2026-05-01", "url": "u"}]},
        }
        sig = build_signals(rep)
        news = next(r for r in sig if r["type"] == "news")
        senior = next(r for r in sig if r["type"] == "senior_hire_req")
        self.assertEqual(news["confidence"], "low")            # ambiguous → downgraded
        self.assertLess(sig.index(senior), sig.index(news))    # primary outranks collision news

    def test_stale_event_not_boosted(self):  # publish-date != event-date
        rep = self._win()
        rep["sources"] = {"news": {"status": "active", "signals": [
            {"title": "Acme raises $25M Series B", "outlet": "TC", "date": "2026-06-01", "url": "a"},
            {"title": "Partner note: Acme recently raised $200M", "outlet": "TC", "date": "2026-06-01", "url": "b"}]}}
        sig = build_signals(rep)
        fresh = next(r for r in sig if "raises $25M" in r["claim"])
        stale = next(r for r in sig if "recently raised" in r["claim"])
        self.assertGreater(fresh["score"], stale["score"])  # stale ("recently") not boosted

    def test_deterministic(self):
        rep = self._win()
        rep["sources"] = {"status": {"status": "active", "signals": [
            {"title": "Outage", "date": "2026-05-01", "url": "s"}]}}
        self.assertEqual([r["score"] for r in build_signals(rep)],
                         [r["score"] for r in build_signals(rep)])

    def test_confidence_labeling(self):
        sig = build_signals(self._report())
        sr = next(r for r in sig if r["type"] == "senior_hire_req")
        self.assertEqual((sr["confidence"], sr["url"], sr["date"]), ("primary", "u1", "2026-05-26"))
        self.assertEqual(next(r for r in sig if r["type"] == "news")["confidence"], "low")  # noisy

    def test_sorted_newest_first(self):
        dated = [r for r in build_signals(self._report()) if r["date"]]
        self.assertEqual(dated, sorted(dated, key=lambda x: x["date"], reverse=True))


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

    def test_clean_title_strips_outlet(self):
        self.assertEqual(news._clean_title("Datadog launches Bits AI - SiliconANGLE", "SiliconANGLE"),
                         "Datadog launches Bits AI")
        self.assertEqual(news._clean_title("No outlet suffix here", "TechCrunch"),
                         "No outlet suffix here")


class TestEdgarMatching(unittest.TestCase):
    """#2: normalized-exact name match — no wrong-entity public routing."""

    def setUp(self):
        edgar._TICKERS_CACHE["ok"] = True
        edgar._TICKERS_CACHE["data"] = {
            "0": {"cik_str": 1561550, "ticker": "DDOG", "title": "Datadog, Inc."},
            "1": {"cik_str": 1, "ticker": "MRCY", "title": "Mercury Systems Inc"},
            "2": {"cik_str": 2, "ticker": "RAMP", "title": "LiveRamp Holdings, Inc."},
            "3": {"cik_str": 3, "ticker": "WAVE", "title": "Wave Life Sciences Ltd."},
            "4": {"cik_str": 4, "ticker": "RELY", "title": "Remitly Global, Inc."},
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

    def test_corporate_tail_match(self):
        m = edgar.lookup_cik("Remitly")  # "Remitly" -> "Remitly Global, Inc." (RELY)
        self.assertIsNotNone(m)
        self.assertEqual(m["ticker"], "RELY")

    def test_tail_allowlist_excludes_systems(self):
        # "systems" is NOT an allowlisted tail even though it's the only candidate.
        edgar._TICKERS_CACHE["data"] = {
            "0": {"cik_str": 9, "ticker": "MRCY", "title": "Mercury Systems, Inc."}}
        self.assertIsNone(edgar.lookup_cik("Mercury"))

    def test_tail_match_requires_uniqueness(self):
        # Two allowlisted-tail candidates for "Acme" → refuse, never guess.
        edgar._TICKERS_CACHE["data"] = {
            "0": {"cik_str": 10, "ticker": "ACG", "title": "Acme Global, Inc."},
            "1": {"cik_str": 11, "ticker": "ACH", "title": "Acme Holdings Corp"}}
        self.assertIsNone(edgar.lookup_cik("Acme"))


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

    def test_pick_brand_prefix_affinity(self):
        # datadoghq slug, "Datadog" candidate → slug starts with candidate.
        self.assertEqual(identity.pick_brand(["Datadog"], "datadoghq"), "Datadog")

    def test_pick_brand_title_segment(self):
        cands = ["Cloud Monitoring as a Service", "Datadog"]  # title split, brand is 2nd
        self.assertEqual(identity.pick_brand(cands, "datadoghq"), "Datadog")

    def test_pick_brand_strips_get_try_prefix(self):
        self.assertEqual(identity.pick_brand(["Paddle"], "trypaddle"), "Paddle")

    def test_pick_brand_rejects_marketing_copy(self):
        self.assertIsNone(identity.pick_brand(["The Modern Observability Platform"], "datadoghq"))

    def test_pick_brand_identity_case(self):
        self.assertEqual(identity.pick_brand(["Stripe"], "stripe"), "Stripe")

    def test_pick_brand_empty(self):
        self.assertIsNone(identity.pick_brand([], "datadoghq"))
        self.assertIsNone(identity.pick_brand(["ab"], "datadoghq"))  # too short

    def test_derive_name_from_og_and_title(self):
        cases = [
            ('<meta property="og:site_name" content="Datadog">', "datadoghq.com", "Datadog"),
            ('<meta content="Datadog" property="og:site_name">', "datadoghq.com", "Datadog"),  # order
            ('<title>Cloud Monitoring as a Service | Datadog</title>', "datadoghq.com", "Datadog"),
            ('<title>Nothing Relevant Here</title>', "datadoghq.com", None),  # no affinity → None
        ]
        orig = identity.fetch_text
        try:
            for html, dom, expect in cases:
                identity.fetch_text = lambda url, **kw: (200, html)
                self.assertEqual(identity.derive_name(dom), expect)
            identity.fetch_text = lambda url, **kw: (0, "")  # homepage unreachable
            self.assertIsNone(identity.derive_name("datadoghq.com"))
        finally:
            identity.fetch_text = orig


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


def _full_report():
    from last_quarter import build_footer
    from lib.signals import build_signals
    rep = {"window": {"start": "2026-04-08", "end": "2026-07-07"},
           "profile": {"name": "Acme", "domain": "acme.com", "public": False, "ticker": None},
           "sources": {
               "careers": {"status": "active", "ats": "ashby", "board_url": "b",
                           "listed_total": 10, "posted_in_window": 5,
                           "dept_concentration": [["Sales", 3]],
                           "senior_roles": [{"title": "VP Sales", "date": "2026-05-01", "url": "u"}],
                           "note": "ATS survivorship caveat."},
               "news": {"status": "active", "noisy": True, "signals": [
                   {"title": "Acme raises $10M Series A", "outlet": "TC", "date": "2026-06-01", "url": "n"}]},
           }}
    rep["sources_active"] = [k for k, v in rep["sources"].items() if v.get("status") == "active"]
    rep["sources_total"] = len(rep["sources"])
    rep["footer"] = build_footer(rep)
    rep["signals"] = build_signals(rep)
    return rep


class TestRenderMd(unittest.TestCase):
    def setUp(self):
        from lib.render_md import render_md
        self.rep = _full_report()
        self.md = render_md(self.rep)

    def test_footer_verbatim_last(self):
        self.assertTrue(self.md.rstrip().endswith(self.rep["footer"]))

    def test_first_top_signal_is_highest_score(self):
        top = [r for r in self.rep["signals"] if r["type"] not in {"tech_stack", "open_roles", "data_caveat"}]
        self.assertIn(top[0]["claim"], self.md.split("## By category")[0])

    def test_excluded_types_not_in_top(self):
        top_section = self.md.split("## Top signals")[1].split("## By category")[0]
        self.assertNotIn("open roles posted in-window", top_section)  # open_roles excluded

    def test_source_note_survives_in_coverage(self):
        self.assertIn("ATS survivorship caveat.", self.md)

    def test_low_confidence_marker(self):
        self.assertIn("⚠ entity-check", self.md)  # noisy news → low conf

    def test_no_ansi(self):
        self.assertNotIn("\x1b", self.md)


class TestWebstack(unittest.TestCase):
    def test_detects_installed_snippets(self):
        from lib import webstack
        html = ('<script src="https://js.intercomcdn.com/frame.js"></script>'
                '<script src="https://cdn.segment.com/analytics.js/v1/x/analytics.min.js"></script>'
                '<link href="https://assets.website-files.com/x.css">')
        tools = {d["tool"] for d in webstack.detect(html, {})}
        self.assertEqual(tools, {"Intercom", "Segment", "Webflow"})

    def test_prose_mention_does_not_match(self):  # signature negative — the "outreach" lesson
        html = "<p>How we integrated Intercom and Segment into our GTM workflow</p>"
        self.assertEqual(from_lib_detect(html, {}), [])

    def test_header_only_detection(self):
        from lib import webstack
        tools = {d["tool"] for d in webstack.detect("", {"cf-ray": "abc123", "x-vercel-id": "xyz"})}
        self.assertEqual(tools, {"Cloudflare", "Vercel"})

    def test_observed_stack_signal_and_corroboration(self):
        rep = {"window": {"end": "2026-07-07", "start": "2026-04-08"},
               "profile": {"name": "Acme", "domain": "acme.com", "public": False, "ticker": None},
               "sources": {
                   "webstack": {"status": "active", "count": 2,
                                "by_category": {"Analytics": ["Segment"], "ABM": ["6sense"]}},
                   "careers": {"status": "active", "ats": "ashby", "board_url": "b",
                               "listed_total": 5, "posted_in_window": 3, "dept_concentration": [],
                               "senior_roles": [{"title": "VP Eng", "date": "2026-06-01", "url": "u"}],
                               "tech_stack": [{"tool": "Segment", "category": "Data"}]},
               }}
        sig = build_signals(rep)
        obs = next(r for r in sig if r["type"] == "observed_stack")
        self.assertEqual(obs["confidence"], "primary")
        self.assertIn("corroborated by JDs: Segment", obs["claim"])
        senior = next(r for r in sig if r["type"] == "senior_hire_req")
        self.assertLess(sig.index(senior), sig.index(obs))  # context never outranks an event


def from_lib_detect(html, headers):
    from lib import webstack
    return webstack.detect(html, headers)


class TestBlogPaths(unittest.TestCase):
    def test_post_link_paths(self):
        from lib.blog import _POST_LINK
        self.assertTrue(_POST_LINK.search('href="/resources/some-guide"'))
        self.assertTrue(_POST_LINK.search('href="/case-studies/acme-inc"'))
        self.assertTrue(_POST_LINK.search('href="/customers/acme-story"'))
        self.assertIsNone(_POST_LINK.search('href="/pricing"'))
        self.assertIsNone(_POST_LINK.search('href="/about"'))


class TestNewsroomBases(unittest.TestCase):
    def test_bases_adds_news_and_press(self):
        from lib.blog import _bases
        b = _bases("remitly.com")
        self.assertEqual(b[0], "https://remitly.com")            # main first
        self.assertIn("https://news.remitly.com", b)
        self.assertIn("https://press.remitly.com", b)

    def test_bases_from_www_and_subdomain(self):
        from lib.blog import _bases
        self.assertEqual(_bases("www.acme.com")[0], "https://www.acme.com")
        self.assertIn("https://news.acme.com", _bases("www.acme.com"))  # registrable, not www
        self.assertIn("https://news.acme.com", _bases("blog.acme.com"))

    def test_is_newsroom(self):
        from lib.blog import _is_newsroom
        self.assertTrue(_is_newsroom("https://news.remitly.com/feed"))
        self.assertTrue(_is_newsroom("https://press.acme.com/rss.xml"))
        self.assertFalse(_is_newsroom("https://acme.com/blog/rss.xml"))
        self.assertFalse(_is_newsroom(""))


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
        self.assertNotIn("paid:", f)  # no paid source ran → no paid line

    def test_footer_paid_line(self):
        report = {"sources": {
            "careers": {"status": "active", "posted_in_window": 9},
            "exa": {"status": "active", "count": 8, "calls": 1},
            "pdl": {"status": "active", "count": 20, "credits_used": 20},
            "blog": {"status": "active", "count": 5, "firecrawl_credits": 1},
        }}
        f = build_footer(report)
        self.assertIn("paid: exa 1 call", f)
        self.assertIn("firecrawl 1 credit", f)
        self.assertIn("pdl 20 credits", f)


class TestCareersProbePriority(unittest.TestCase):
    """Concurrent 3-ATS probing must still select by FIXED priority (ashby>greenhouse>lever),
    never by which future finished first — so output is deterministic."""

    def test_ashby_wins_over_greenhouse(self):
        import lib.careers as C
        orig = (C._ashby, C._greenhouse, C._lever)
        try:
            C._ATS_PARSERS = [("ashby", lambda t: {"ats": "ashby"}),
                              ("greenhouse", lambda t: {"ats": "greenhouse"}),
                              ("lever", lambda t: None)]
            board, tried = C._probe_token("acme")
            self.assertEqual(board["ats"], "ashby")            # priority, not first-done
            self.assertEqual(tried, ["ashby:acme", "greenhouse:acme", "lever:acme"])
        finally:
            C._ATS_PARSERS = [("ashby", orig[0]), ("greenhouse", orig[1]), ("lever", orig[2])]

    def test_lever_wins_when_only_hit(self):
        import lib.careers as C
        orig = (C._ashby, C._greenhouse, C._lever)
        try:
            C._ATS_PARSERS = [("ashby", lambda t: None),
                              ("greenhouse", lambda t: None),
                              ("lever", lambda t: {"ats": "lever"})]
            board, tried = C._probe_token("acme")
            self.assertEqual(board["ats"], "lever")
        finally:
            C._ATS_PARSERS = [("ashby", orig[0]), ("greenhouse", orig[1]), ("lever", orig[2])]

    def test_all_miss_returns_none(self):
        import lib.careers as C
        orig = (C._ashby, C._greenhouse, C._lever)
        try:
            C._ATS_PARSERS = [(n, lambda t: None) for n in ("ashby", "greenhouse", "lever")]
            board, tried = C._probe_token("acme")
            self.assertIsNone(board)
            self.assertEqual(len(tried), 3)
        finally:
            C._ATS_PARSERS = [("ashby", orig[0]), ("greenhouse", orig[1]), ("lever", orig[2])]


class TestJsonSidecar(unittest.TestCase):
    """Lever 2: one --emit md run also writes the full report JSON to disk so the agent
    never re-runs the engine with --emit json."""

    def test_sidecar_writes_parseable_json(self):
        import json
        from last_quarter import write_json_sidecar
        rep = _full_report()
        path = write_json_sidecar(rep)
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertIn("signals", loaded)
        self.assertIn("footer", loaded)
        self.assertEqual(loaded["profile"]["domain"], rep["profile"]["domain"])

    def test_md_keeps_footer_last_and_has_sidecar_comment(self):
        from lib.render_md import render_md
        from last_quarter import _inject_sidecar_comment
        rep = _full_report()
        md = _inject_sidecar_comment(render_md(rep), "/tmp/last-quarter/x.json")
        self.assertIn("<!-- full engine JSON", md)              # comment present
        self.assertLess(md.index("<!-- full engine JSON"),      # near the top, under Profile
                        md.index("## Top signals"))
        self.assertTrue(md.rstrip().endswith(rep["footer"]))    # footer still the final block


_WIN = {"start": "2026-04-14", "end": "2026-07-13",
        "prior_start": "2026-01-14", "prior_end": "2026-04-14"}


class TestWorkdayDates(unittest.TestCase):
    def test_relative_date_conversion(self):
        from datetime import date as _date
        from lib.workday import _posted_date
        today = _date(2026, 7, 13)
        self.assertEqual(_posted_date("Posted Today", today), "2026-07-13")
        self.assertEqual(_posted_date("Posted Yesterday", today), "2026-07-12")
        self.assertEqual(_posted_date("Posted 3 Days Ago", today), "2026-07-10")
        self.assertIsNone(_posted_date("Posted 30+ Days Ago", today))  # floor, not a date
        self.assertIsNone(_posted_date("Just posted", today))
        self.assertIsNone(_posted_date(None, today))

    def test_site_candidates_hint_first(self):
        from lib.workday import _site_candidates
        c = _site_candidates("remitly", "Remitly_Careers")
        self.assertEqual(c[0], "Remitly_Careers")
        self.assertIn("Careers", c)


class TestWorkdayCollect(unittest.TestCase):
    def test_parses_paginates_and_drops_floor_dates(self):
        import lib.workday as W

        def _page(offset, posted):
            return {"total": 45, "jobPostings": [
                {"title": f"Role {i}", "externalPath": f"/job/x/R{i}",
                 "locationsText": "Remote", "postedOn": posted}
                for i in range(offset, min(offset + 20, 45))]}
        pages = {0: _page(0, "Posted 2 Days Ago"), 20: _page(20, "Posted 40 Days Ago"),
                 40: _page(40, "Posted 30+ Days Ago")}
        calls = []

        def fake_post(url, payload, *, headers=None, timeout=25):
            calls.append(payload["offset"])
            return 200, pages.get(payload["offset"])

        def fake_fetch_json(url, **kw):
            return 200, {"jobPostingInfo": {"jobDescription": "<p>Python and Go</p>",
                                            "startDate": "2026-07-11"}}
        orig = (W.post_json, W.fetch_json)
        try:
            W.post_json, W.fetch_json = fake_post, fake_fetch_json
            board = W.collect("acme", "5", "Acme_Careers", _WIN)
        finally:
            W.post_json, W.fetch_json = orig
        self.assertIsNotNone(board)
        self.assertEqual(board["ats"], "workday")
        self.assertEqual(board["token"], "acme:wd5:Acme_Careers")
        self.assertEqual(len(board["jobs"]), 45)
        self.assertEqual(sorted(set(calls)), [0, 20, 40])           # paginated every page
        self.assertEqual(sum(1 for j in board["jobs"] if j["date"]), 40)  # 5 "30+" dropped
        self.assertIn("LOWER BOUND", board["note"])

    def test_dept_facets_extracted(self):
        import lib.workday as W

        def fake_post(url, payload, *, headers=None, timeout=25):
            if payload["offset"] != 0:
                return 200, {"total": 3, "jobPostings": []}
            return 200, {"total": 3, "jobPostings": [
                {"title": "Eng", "externalPath": "/job/x/R1", "locationsText": "NYC",
                 "postedOn": "Posted 2 Days Ago"}],
                "facets": [{"facetParameter": "jobFamilyGroup", "descriptor": "Job Category",
                            "values": [{"descriptor": "Engineering", "count": 47},
                                       {"descriptor": "Compliance", "count": 16}]}]}
        orig = (W.post_json, W.fetch_json)
        try:
            W.post_json = fake_post
            W.fetch_json = lambda url, **kw: (200, {"jobPostingInfo": {"jobDescription": "x"}})
            board = W.collect("acme", "5", "Acme_Careers", _WIN)
        finally:
            W.post_json, W.fetch_json = orig
        self.assertEqual(board["dept_facets"], [("Engineering", 47), ("Compliance", 16)])


class TestBoardDiscovery(unittest.TestCase):
    def test_workday_link_and_site_hint(self):
        from lib.careers import _WD_LINK, _wd_site_hint
        m = _WD_LINK.search("https://remitly.wd5.myworkdayjobs.com/en-US/Remitly_Careers/job/x")
        self.assertEqual((m.group(1), m.group(2)), ("remitly", "5"))
        self.assertEqual(_wd_site_hint(m.group(3)), "Remitly_Careers")  # skips en-US + /job

    def test_contamination_guard_two_distinct_boards(self):
        import lib.careers as C
        html = ('<a href="https://boards.greenhouse.io/foo">x</a>'
                '<a href="https://acme.wd5.myworkdayjobs.com/Acme">y</a>')
        orig = C.fetch_text
        try:
            C.fetch_text = lambda url, **kw: (200, html)
            board, via, pages, unsup = C._discover_board("test.com", _WIN)
        finally:
            C.fetch_text = orig
        self.assertIsNone(board)  # two distinct boards on one page → refuse

    def test_unsupported_ats_surfaced(self):
        import lib.careers as C
        orig = C.fetch_text
        try:
            C.fetch_text = lambda url, **kw: (200, '<iframe src="https://acme.icims.com/jobs">')
            _, _, _, unsup = C._discover_board("acme.com", _WIN)
        finally:
            C.fetch_text = orig
        self.assertEqual(unsup, "iCIMS")

    def test_smartrecruiters_and_recruitee_links_resolve(self):
        from lib.careers import _ATS_LINK
        self.assertEqual(_ATS_LINK["smartrecruiters"].search(
            "https://jobs.smartrecruiters.com/Visa/744000").group(1), "Visa")
        self.assertEqual(_ATS_LINK["recruitee"].search(
            "https://personio.recruitee.com/o/api-job").group(1), "personio")


class TestNewATSParsers(unittest.TestCase):
    def test_smartrecruiters_shape(self):
        import lib.careers as C
        payload = {"content": [{"name": "Staff Engineer", "id": "744",
                                "releasedDate": "2026-06-24T10:00:11Z",
                                "location": {"fullLocation": "Austin, TX, United States"},
                                "department": {"label": "Engineering"}}]}
        orig = C.fetch_json
        try:
            C.fetch_json = lambda url, **kw: (200, payload)
            board = C._smartrecruiters("visa")
        finally:
            C.fetch_json = orig
        self.assertEqual(board["ats"], "smartrecruiters")
        j = board["jobs"][0]
        self.assertEqual(j["title"], "Staff Engineer")
        self.assertEqual(j["department"], "Engineering")
        self.assertEqual(j["location"], "Austin, TX, United States")
        self.assertIn("jobs.smartrecruiters.com/visa/744", j["url"])

    def test_recruitee_shape_and_utc_date(self):
        import lib.careers as C
        payload = {"offers": [{"title": "Backend Eng", "department": "Produkt",
                               "location": "Berlin, Germany", "careers_url": "https://x.recruitee.com/o/1",
                               "published_at": "2026-05-02 14:19:26 UTC",
                               "description": "<p>Python</p>", "requirements": "<p>Go</p>"}]}
        orig = C.fetch_json
        try:
            C.fetch_json = lambda url, **kw: (200, payload)
            board = C._recruitee("acme")
        finally:
            C.fetch_json = orig
        j = board["jobs"][0]
        self.assertEqual(j["title"], "Backend Eng")
        self.assertEqual(j["department"], "Produkt")
        self.assertEqual(j["date"], "2026-05-02 14:19:26")  # " UTC" stripped for parse_dt
        self.assertIn("Python", j["text"])

    def test_empty_returns_none(self):
        import lib.careers as C
        orig = C.fetch_json
        try:
            C.fetch_json = lambda url, **kw: (200, {"content": []})
            self.assertIsNone(C._smartrecruiters("nobody"))
            C.fetch_json = lambda url, **kw: (200, {"offers": []})
            self.assertIsNone(C._recruitee("nobody"))
        finally:
            C.fetch_json = orig


class TestJsonLdJobs(unittest.TestCase):
    def test_graph_wrapper_extraction(self):
        from lib.jsonld_jobs import _extract
        html = ('<script type="application/ld+json">'
                '{"@graph":[{"@type":"JobPosting","title":"Eng","datePosted":"2026-06-01"}]}'
                '</script>')
        jps = _extract(html)
        self.assertEqual(len(jps), 1)
        self.assertEqual(jps[0]["title"], "Eng")

    def test_entity_guard(self):
        from lib.jsonld_jobs import _entity_ok
        want = {"remitly"}
        self.assertFalse(_entity_ok({"hiringOrganization": {"name": "Stripe Inc"}}, want))
        self.assertTrue(_entity_ok({"hiringOrganization": {"name": "Remitly"}}, want))
        self.assertTrue(_entity_ok({"title": "x"}, want))  # no org named → trust the page

    def test_collect_listing_shape(self):
        from lib.jsonld_jobs import collect
        html = ('<script type="application/ld+json">'
                '[{"@type":"JobPosting","title":"Backend Eng","datePosted":"2026-06-20","url":"/j/1"},'
                '{"@type":"JobPosting","title":"PM","datePosted":"2026-06-21","url":"/j/2"}]</script>')
        board = collect("acme.com", "Acme", _WIN, {"/careers": html})
        self.assertEqual(board["ats"], "json-ld")
        self.assertEqual(len(board["jobs"]), 2)
        self.assertEqual({j["date"] for j in board["jobs"]}, {"2026-06-20", "2026-06-21"})
        self.assertEqual({j["title"] for j in board["jobs"]}, {"Backend Eng", "PM"})


if __name__ == "__main__":
    unittest.main()
