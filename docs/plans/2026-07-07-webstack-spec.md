# Implementation Spec: `webstack` — stdlib website-technographics fingerprint matcher

**Date:** 2026-07-07
**For:** the implementing model (Opus). Execute exactly; decisions are made.
**Repo:** `~/Desktop/fun-projects/random-shit/last-quarter-skill` (`main`, private).

## Context & decision (don't re-litigate)

We want website technographics (what's *observably deployed* on the company's site:
Intercom, Segment, HubSpot vs Marketo, 6sense, Webflow…) as a FREE source. External tools
(projectdiscovery httpx / wappalyzergo) were REJECTED — they're Go, and the engine's hard
principle is stdlib-Python, zero deps, no binaries to install. Instead: a ~60-line curated
fingerprint matcher over one homepage GET.

This complements JD mining, it doesn't replace it: **JD stack = stated** (what job ads say
engineers use), **webstack = observed** (what's actually installed on the site). A tool in
BOTH is our highest-confidence technographic claim.

House rules (same as all prior specs): stdlib only · precision-first with negative-guard
tests (the signature test style: a *prose mention* must NOT match) · hermetic test suite
(`python3 -m unittest test_engine` from `engine/`, currently 66 pass, no network/keys) ·
never weaken existing guards · stdout purity · `.env` never staged · `--today 2026-07-07`
for live runs · commit style per `git log`.

---

## Task 1 — `http.fetch_full`: expose response headers

`engine/lib/http.py`: add

```python
def fetch_full(url, *, timeout=12, headers=None, maxbytes=None):
    """GET → (status_code, body_bytes, resp_headers_lowercased_dict). Never raises."""
```

Same error philosophy as `fetch` (transport failure → `(0, b"", {})`). Lowercase all
response-header names. Do NOT change existing `fetch`/`fetch_json` signatures.

## Task 2 — `engine/lib/webstack.py`

### Fingerprint set (curated, GTM-relevant, DOMAIN-ANCHORED)

**The one precision rule that matters:** never match tool *names* — a blog post saying
"we integrated Intercom" must not fire (the JD-mining "outreach"-noun trap). Match vendor
CDN domains / script paths that only appear when the snippet is actually installed.

Module-level table `FINGERPRINTS: {name: (category, regex_str)}` — body patterns
(compile with `re.I`; substring-prefilter with a lowercase literal before regex, same perf
pattern as jd_mining):

- Analytics: GoogleAnalytics/GTM `googletagmanager\.com`, Segment `cdn\.segment\.com`,
  Amplitude `cdn\.amplitude\.com`, Mixpanel `cdn\.mxpnl\.com`, PostHog
  `[a-z0-9.-]*posthog\.com/`, Heap `cdn\.heapanalytics\.com`, Hotjar `static\.hotjar\.com`,
  FullStory `edge\.fullstory\.com`, Plausible `plausible\.io/js`
- Marketing/CRM: HubSpot `js\.hs-scripts\.com|js\.hsforms\.net|js\.hs-analytics\.net`,
  Marketo `munchkin\.marketo\.net`, Klaviyo `static\.klaviyo\.com`, Pardot `pi\.pardot\.com`,
  LinkedIn Insight `snap\.licdn\.com`, Meta Pixel `connect\.facebook\.net`,
  Clearbit `tag\.clearbitscripts\.com`
- **ABM (the spicy category):** 6sense `j\.6sc\.co`, Demandbase `tag\.demandbase\.com`,
  Mutiny `mutinycdn\.com`, Qualified `js\.qualified\.com`, Koala `cdn\.getkoala\.com`
- Support/Chat: Intercom `widget\.intercom\.io|js\.intercomcdn\.com`, Drift `js\.driftt\.com`,
  Zendesk `static\.zdassets\.com`, Crisp `client\.crisp\.chat`
- Scheduling/Demo: Calendly `assets\.calendly\.com`, Chili Piper `chilipiper\.com`,
  Navattic `js\.navattic\.com`, Storylane `js\.storylane\.io`
- CMS/Framework: Webflow `assets\.website-files\.com|data-wf-domain`, WordPress
  `/wp-content/`, Shopify `cdn\.shopify\.com`, Contentful `ctfassets\.net`, Sanity
  `cdn\.sanity\.io`, Framer `framerusercontent\.com`, Next.js `/_next/static/`,
  Nuxt `/_nuxt/`, Gatsby `id="___gatsby"`
- A/B: Optimizely `cdn\.optimizely\.com`, VWO `visualwebsiteoptimizer\.com`
- Payments: Stripe `js\.stripe\.com`

Header table `HEADER_FPS: {name: (category, header_name, regex_or_None)}` (match against
the lowercased header dict; regex=None → presence suffices):

- Cloudflare → `cf-ray` present (or `server` ~ `cloudflare`)
- Vercel → `x-vercel-id` present
- Netlify → `x-nf-request-id` present (or `server` ~ `netlify`)
- Fastly → `x-served-by` ~ `fastly`
- CloudFront → `via` ~ `cloudfront` (or `x-amz-cf-id` present)
- Fly.io → `fly-request-id` present

If a specific pattern doesn't fire on a live site during Task 5, fix by *tightening/replacing
the domain pattern* after inspecting the real HTML — NEVER by falling back to name-matching.

### API

```python
def detect(html: str, headers: dict) -> list[dict]:
    # pure, offline-testable → [{"tool","category","evidence"}]  evidence = matched literal/header

def collect(domain: str) -> dict:
    # one fetch_full("https://{registrable_domain}", maxbytes=300_000); on code 0 → status
    # "error" (honest, not empty); no hits → "empty". Active shape:
    # {"source":"webstack","status":"active","count":N,
    #  "by_category": {"Analytics":["Segment",...], "ABM":[...], ...},   # ordered dict
    #  "signals": [{"title": "Analytics: Segment, Amplitude"}, ...],     # one per category,
    #  "note": "Observed on the live site (fingerprinted script/header evidence)."}
```

The `signals` list of per-category one-liners exists so the compact view's generic loop
renders it with zero special-casing.

## Task 3 — Integration

- **Registry:** `Source("webstack", "free", lambda c: webstack.collect(c.domain))` —
  placed after `hackernews`. Footer/`SOURCE_ORDER` pick it up automatically; verify the
  footer shows `webstack ✓ N`.
- **signals[]** (`lib/signals.py`): ONE aggregated record (not per-tool spam):
  `type="observed_stack"`, `category="tech"`, weight 2 (add to `_TYPE_WEIGHT`),
  `confidence="primary"`, `claim="Observed on site — Analytics: Segment · ABM: 6sense · …"`
  (join by_category, cap ~200 chars), `url=f"https://{domain}"`, no date.
  **Corroboration:** intersect webstack tool names with `careers.tech_stack[].tool`
  (case-insensitive); if non-empty, append ` (corroborated by JDs: X, Y)` to the claim.
- **compact:** nothing to do beyond the generic loop — add `("webstack", "SITE")` to the
  label tuple in `compact()`.
- **`render_md`:** in By-category, after the Stack line: `- **Observed on site:** …` from
  `by_category` (omit when webstack not active). Coverage section picks up its `note`
  automatically via SOURCE_ORDER.
- **SKILL.md:** one bullet in the source list + Output Contract Hiring/tech area:
  "webstack = observed website technographics (script/header fingerprints, domain-anchored;
  stated-vs-observed distinction; corroborated tools flagged)".
- **`--diagnose`:** add a `webstack` probe: `detect()` against a live fetch of
  `https://www.vanta.com` asserting ≥1 detection (fingerprint-rot canary).

## Task 4 — Tests (all offline; extend `test_engine.py`)

1. Fixture HTML containing real snippet URLs
   (`<script src="https://js.intercomcdn.com/x.js">`, `cdn.segment.com/analytics.js`,
   `assets.website-files.com/...css`) → Intercom + Segment + Webflow detected, right categories.
2. **Prose negative (signature test):** `"<p>How we integrated Intercom and Segment into
   our workflow</p>"` → `detect` returns NOTHING.
3. Header-only: `{"cf-ray": "abc", "x-vercel-id": "xyz"}` with empty body → Cloudflare + Vercel.
4. `collect`-shape unit-test via `detect` only (no network in tests); verify signals list is
   per-category one-liners.
5. signals[] corroboration: report fixture with webstack(Segment) + careers.tech_stack
   containing Segment → claim contains "corroborated by JDs: Segment"; record has
   score/uniform keys; weight-2 (an `observed_stack` never outranks a `senior_hire_req` —
   assert ordering).

## Task 5 — Live checks (free only, paste lines into summary)

Run `--emit compact --quiet` with `--today 2026-07-07` for: `vanta.com` (expect Webflow +
marketing/ABM tags), `posthog.com` (expect PostHog itself + framework), `mybrightwheel.com`.
Paste each SITE line. If a listed fingerprint should obviously fire but doesn't, inspect the
fetched HTML and tighten the pattern (rule above). Also run `--diagnose` and paste the
webstack row. One `--emit md` run (linear.app) to show the "Observed on site" bullet.

## Task 5.5 — Output-sense review (MANDATORY — "does this output make sense for us?")

Detection working ≠ output useful. After the live checks, run this review and include an
**OUTPUT SENSE REVIEW** section in your final summary. Four checks per company:

1. **Evidence audit (correctness).** For EVERY live detection, grep the fetched HTML for
   the matched evidence literal and confirm it sits in a `src=`/`href=`/script context —
   not prose, not a code sample in a blog snippet, not an HTML comment. One wrong-entity
   or prose-matched detection = fix the pattern before committing (tighten, never loosen).

2. **Plausibility cross-check (truth).** Sanity-check detections against what we
   independently know: posthog.com should detect PostHog (they dogfood) and plausibly a
   modern framework; vanta.com is a Webflow-built site; a detection like "Shopify on
   vanta.com" is implausible → investigate before trusting the matcher. Volume sanity:
   a typical B2B SaaS homepage yields ~4–12 detections. 0 across all three companies =
   matcher too tight (broken); 25+ = too loose. Either extreme fails the review.

3. **GTM-usefulness bar (the "for us" question).** Read each company's SITE line and ask:
   *would an SDR or competitive-intel user change their email or battlecard because of
   this?* Detections in Marketing/CRM, ABM, Support, Scheduling, and corroborated tools
   pass this bar. If a company's line is ONLY infra/framework (Cloudflare, Next.js),
   that's honest-but-weak — acceptable, but if GTM-relevant categories fire on ZERO of
   the three test companies, the fingerprint set is miscalibrated for our use case:
   inspect the fetched HTML for common GTM snippets we missed, add (domain-anchored)
   fingerprints for what's actually there, and re-run. Do not ship a matcher that only
   ever says "they use Cloudflare."

4. **Coherence with the rest of the report.** Does the SITE line contradict or duplicate?
   Corroboration should plausibly fire somewhere (JDs mentioning HubSpot + HubSpot on
   site); if it never fires across all three, suspect a name-normalization bug in the
   intersection. Confirm the aggregated signal lands in `signals[]` with weight 2 and
   never outranks event signals in `--emit md` Top signals (it's context, not a why-now —
   it belongs in By-category only; verify it's excluded from Top signals or naturally
   ranks below them).

Verdict format in the summary, per company:
`{domain}: N detections · evidence-verified ✓/✗ · plausible ✓/✗ · GTM-useful ✓/~/✗`
plus one overall line: KEEP / TUNED (what changed) / and any detection you removed as a
false positive. If the honest verdict is "technically correct but useless garnish," SAY
THAT — do not dress it up; the user decides whether it stays in the launch.

## Definition of done

- [ ] Tasks 1–4 implemented; suite green + ~7 new tests, still hermetic
- [ ] Task 5 live checks pasted; fingerprints adjusted only by tightening
- [ ] Task 5.5 OUTPUT SENSE REVIEW included in the final summary (per-company verdicts +
      overall KEEP/TUNED; honest call if the output is correct-but-useless)
- [ ] SKILL.md + diagnose updated; footer shows webstack
- [ ] `.env` never staged; ONE commit; push origin main
- [ ] Memory file updated (webstack shipped — free technographics, observed-vs-stated,
      corroboration; next = Phase B packaging/publish)

## Out of scope

- No httpx / wappalyzergo / any binary or pip dep. No full Wappalyzer DB vendoring (curated
  set only). No stack-diff-over-time (delta rejected). No new paid sources. No per-tool
  signal records (one aggregate). Don't touch existing guards, ranking weights (beyond
  adding `observed_stack: 2`), or Phase B items.
