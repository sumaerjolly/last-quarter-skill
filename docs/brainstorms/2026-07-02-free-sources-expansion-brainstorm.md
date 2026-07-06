# Brainstorm: Free Source Expansion

**Date:** 2026-07-02
**Status:** Brainstorm — free-tier only (paid track is separate)
**Context:** Extends the `last-quarter` skill/engine. Paid sources (Sumble/PDL/Crustdata/
Exa/Firecrawl/Apify, optionally via Printing Press CLIs) are a separate brainstorm.

---

## What We're Building

More **free (no-key) source collectors** for the engine, prioritized by **which signal
category they fill**, not by "more sources." Everything stays stdlib-only so the free
tier keeps working with zero setup.

## Current coverage → gaps

| Signal category | Current free sources | Strength |
|---|---|---|
| Hiring (open roles) | ATS (Ashby/Greenhouse/Lever) | strong, but **coverage misses** (custom ATS) |
| Product launches | blog RSS+HTML, GitHub releases, news | strong |
| Funding / M&A | EDGAR (public), news | ok |
| Leadership | news only | **weak** |
| Expansion / positioning | careers geo hints only | **weak** |
| Risk / negative | news only | **weak** (always "none surfaced") |

Priority = fill the weak rows (Risk, Leadership, Expansion) before piling onto strong ones.

## Tier 1 — build now (fills the gaps)

1. **Status / incident feeds → Risk.** `status.{domain}/history.rss` (Atlassian Statuspage,
   Instatus, BetterStack). *Verified:* AirOps, Datadog, GitHub, OpenAI, Linear. Needs
   discovery: try `status.{domain}` (follow redirects) → `{brand}.statuspage.io` →
   `{brand}status.com`; accept misses (Ramp/Brightwheel have none).
2. **ATS token-discovery + more providers → Hiring coverage.** Crawl `/careers`, detect the
   embedded ATS widget, extract the board token — unlocks all providers at once (would've
   found Increase's Lever board). Add SmartRecruiters (live), Workable, Recruitee, BambooHR,
   Rippling. The discovery step is the real unlock, not provider count.
3. **Press / newsroom scan → Leadership/Funding (primary source).** Extend the blog HTML-
   listing collector to also scan `/press`, `/news`, `/newsroom`. Primary-source releases
   beat aggregators for exec changes, funding, partnerships.
4. **Hacker News (Algolia API) → Launches/discussion.** `hn.algolia.com/api/v1/
   search_by_date?query={co}&numericFilters=created_at_i>{ts}`. *Verified* (20 hits). Free.

## Tier 2 — high value, more effort

5. **EDGAR Form 4 + earnings dates** (public cos) — insider buying/selling (Datadog's
   "$90m") + quarterly financial facts via `data.sec.gov/api/xbrl/...`.
6. **Wayback pricing/positioning diff → Expansion. MOSTLY REJECTED as free (tested 2026-07-03).**
   CDX change-COUNTS are reliable (Vanta pricing 4×, Ramp 5×, AirOps home 14× in-window) but
   that's a weak, noisy "changed N times" signal (A/B tests, embedded timestamps inflate it).
   RICH extraction fails where it matters: pricing pages are JS SPAs → archived HTML is a
   shell → prices leak as noisy unlabeled tokens, no plan names; homepage title/meta extracted
   for Vanta but returned None for AirOps/Stripe/Brightwheel (partial captures / redirects /
   sparse coverage). Verdict: the emailable "repositioned X→Y / added Enterprise tier" signal
   needs **Firecrawl (paid)** to render current + archived pages cleanly and diff — moved to
   the paid tier. Optional free crumb: CDX change-velocity as a labeled low-confidence nudge.
7. ~~**Wikidata / Wikipedia → Profile + funding baseline.**~~ **REJECTED (tested 2026-07-03).**
   Coverage collapses for private cos: Linear/Vanta/Ramp/Increase have NO entity; "AirOps"
   resolved to a plant genus. Even where present (Brightwheel, public Datadog) only
   `founded` is populated — CEO/employees/funding all empty. Static + sparse + wrong-entity
   risk. Not worth wiring. (Also kills podcasts' exec-name dependency — no CEO data.)
8. **iOS App Store lookup → product cadence + rating (mobile/consumer cos).**
   `itunes.apple.com/search?term={co}&entity=software`. *Verified:* Brightwheel v3.100.0,
   4.93★ (136k), updated 2026-06-25. Free, no key.
9. **YouTube channel RSS → launch/webinar videos.** `youtube.com/feeds/videos.xml?
   channel_id={id}` (needs channel-id resolution).

## GTM-hat tier — sources framed by the SDR's actual questions (added 2026-07-02)

Framing: the report answers "what happened"; the SDR still needs (1) an opener, (2) tech
compatibility, (3) budget/momentum proof, (4) what's coming next. Two verified live:

**A. JD mining → free technographics + stated priorities. ✅ VERIFIED — zero new fetches.**
We already download the JDs and throw them away. Ashby returns `descriptionPlain`
(AirOps: 13/13 jobs → Claude ×6, LLM, Figma, Notion, Amplitude, Clay = "Anthropic shop");
Greenhouse `?content=true` returns full JD **and populates departments** (Datadog: 410/410;
Python 17, Go 16, AWS 9, K8s 8) — same param also fixes the dept-null bug. Extract: tech
mentions, priority sentences ("you'll lead our EU expansion"), quota-carrying-req counts.
*Caveat:* needs disambiguation like news — "outreach" ×9 in AirOps JDs is the noun, not
Outreach.io. Match against a curated tool lexicon, not bare words.

**B. Exec podcast/media appearances → the opener. CONDITIONAL — deprioritized (tested 2026-07-03).**
iTunes Search API is free and high-CEILING (exec hits like Karri Saarinen/Linear and
Christina Cacioppo/Vanta are perfect openers). BUT: company-name search is too noisy for
common words (Linear/Vanta/Ramp = mostly garbage); ~50% of execs return 0 (Glyman, Vasen,
Pomel — even big-co CEOs); vertical SaaS (Brightwheel) = 0. Precise recipe needs the
EXEC NAME + company co-occurrence filter — but Wikidata can't supply exec names (rejected
above), so there's no free exec-name source. Revisit only if an exec-name source appears.

**C. USPTO trademark filings → earliest launch signal.** Free API; product names are
trademarked *before* launch (an "AirOps Quill" filing would precede the May 13 launch).
Legal-grade, dated, primary. (Unverified — probe in planning.)

**D. Fast follows (cheap, unverified):** crt.sh new subdomains (eu./developers. =
expansion; promote from Tier 3) · npm/PyPI download trends (dev-tool traction: "SDK
downloads +40% QoQ") · sitemap.xml `lastmod` mining (which product areas active) ·
DNS/MX/TXT tool detection (email/marketing stack, instant) · Cloudflare Radar domain-rank
trend (free traffic proxy) · founder Substack RSS · Discord widget/subreddit stats
(community trend) · USAspending.gov/SAM.gov (gov-contract revenue events).

**GTM-hat top 3 if forced to choose:** JD mining (data already in hand) → podcasts
(opener) → USPTO trademarks (earliest signal anywhere).

## Tier 3 — situational / optional

- **Product Hunt** (free dev token) → startup launches.
- **Reddit search JSON** (`reddit.com/search.json?q={co}`) → sentiment/complaints (Risk).
- **PatentsView patents** → R&D direction for deep-tech targets.

## Key Decisions

- **Free-only, stdlib-only** — no keys, no pip deps; free tier must keep standing alone.
- **Prioritize weak categories** (Risk/Leadership/Expansion) over strong ones.
- **Discovery steps are the unlock** — status-page discovery and ATS token-discovery matter
  more than raw endpoint count.
- **Refactor to a source registry** as part of Tier 1 — going 5 → ~14 sources, the
  orchestrator's hardcoded task list won't scale. Each collector declares
  `{tier, applies_if(profile), ...}`; fan-out + footer become data-driven.
- **Reuse the HTML-listing extractor** (schema.org/OG/`<time>`) for press/newsroom — it
  already generalizes across sites (proven on AirOps/Ramp/Notion).

## Open Questions

1. **Build order:** all of Tier 1 together, or start with the two pure gap-fillers
   (**status feeds + press scan**) since Risk/Leadership are the weakest? *(Lean: registry
   refactor first, then status + press + HN, then ATS discovery.)*
2. **Registry now or later?** Refactor before adding, or add 1–2 more then refactor?
   *(Lean: refactor first — cheaper now than after 9 more collectors.)*
3. **Press scan:** extend the blog collector vs a separate `press` collector? *(Lean:
   extend — same HTML-listing logic, just more paths.)*

## Next

Resolve the 3 open questions, then `/ce:plan` (or implement Tier 1 directly, since the
engine pattern is established).
