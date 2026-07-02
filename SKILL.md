---
name: last-quarter
description: Use when researching what a single company did over the last ~90 days to find outbound/ABM angles — product launches, hiring, funding, leadership changes, expansion, or risk signals — for an SDR or AE preparing cold outreach or account research ("why now", trigger events, buying signals, "what happened at X recently", "prep me for a call with").
---

# Last Quarter

## Overview

Given ONE company domain, produce a **neutral, cited signal report** of what the company
*did* over the trailing ~90 days, so a seller can pick their own "why now" angle.

**Core principle:** **every claim carries an inline source URL + date, or it doesn't
ship.** A rep pastes these into emails — a hallucinated or stale signal gets them
burned. Trust is the product.

**Go to structured primary sources, not scrapers or aggregators.** The failure mode
this skill exists to prevent: an agent scrapes a JS careers page, gives up, and reports
a fuzzy "~30 roles" from an aggregator — when the ATS JSON API returns 13 exact roles
with departments and post dates, for free. Always prefer the API.

## When to Use

- "What's happening at {company} lately / this quarter?" for outbound or account prep
- Building a "why now" / trigger-event angle before a cold email or call
- Single company only. (No list/batch mode — this is for the individual SDR/AE.)

## How to Run (engine first)

**Default path — run the engine.** A stdlib-only Python engine (no `pip install`) fans
out every source concurrently and returns structured JSON in ~7 seconds. Run it from the
directory containing this SKILL.md:

```bash
python3 engine/last_quarter.py {domain} --name "{Company}" --today {YYYY-MM-DD} --json
```

- `--today` = today's date (so the window is deterministic). Omit to use the system date.
- `--keywords "fintech OR banking"` — **required for common-word names** (Increase, Ramp,
  Notion…) or news is unfilterable noise. The engine flags `noisy: true` when it applies.
- Drop `--json` for a human-readable `compact` summary while debugging.

The JSON has `window`, `profile` (public/private routing), `sources_active`, and per
source (`careers`, `news`, `blog`, `edgar`, `github`) the dated signals + a `status` and
`note`. **Synthesize the report (Output Contract below) from that JSON** — one pass, no
re-fetching. Respect each source's `note` (survivorship-bias caveat, noisy-news warning,
SDK-cadence note) and the `sources_active` count for the coverage line.

**Manual fallback.** If `python3` is unavailable, or a source comes back `empty`/`error`
and you want to dig further (e.g. a feedless blog whose `/blog` HTML needs a direct
`WebFetch`, or paid Firecrawl/Exa depth), use the source recipes below — they are the
exact spec the engine implements.

## The Pipeline (what the engine implements)

Run these steps in order. Steps 2–5 can run in parallel once routing is known.

### 1. Profile & route (do this first)

Derive the window from today's date: **trailing 90 days** (state the exact `YYYY-MM-DD
→ YYYY-MM-DD` window in the report header).

Classify the company so you don't waste calls or surface noise:

| Check | How | Switches ON |
|---|---|---|
| **Public?** | Look up name in `sec.gov/files/company_tickers.json`. Hit = public. | EDGAR filings + earnings news |
| **Private?** | Miss in ticker file | **Skip EDGAR.** Careers + news + blog carry it. |
| **Dev-tool?** | Has a public GitHub org / technical product | GitHub releases |

**Careers + Google News RSS are always-on**, regardless of profile.

### 2. Careers (the richest free signal — start here)

Resolve the ATS from the domain's brand token (`airops.com` → `airops`). Try Ashby,
Greenhouse, Lever; **accept the first that returns a NON-EMPTY jobs array** (a `200`
with `[]` or a tiny body is a dead board — Lever does this). Endpoints, fields, and the
date-field names for trajectory are in **references/sources.md**.

Report: listed role count, **how many posted in-window** (bucket by post date),
department concentration of recent reqs, and standout senior/leadership roles. No ATS
hit → the company uses a custom/Workday ATS: fall back to Google News + a `WebFetch` of
the `/careers` page (Firecrawl if it's an empty JS shell).

### 3. News (always-on)

**Google News RSS** first: `news.google.com/rss/search?q="{Company}" when:90d`. Parse
`<item>` title/link/pubDate. GDELT is a throttled backup (1 req / 5s). **Entity-check
every hit** — generic company names collide; confirm the article is about *this* company
before including it.

**Expect thin news for private / non-newsy vertical SaaS** — RSS + GDELT often return
almost nothing. When both are empty, **run one WebSearch pass** for
`{company} funding OR layoffs OR "new VP" OR acquisition` to affirmatively check for
funding, leadership, and negative events. Empty feeds mean "look harder," not "nothing
happened" — never infer absence of a signal from two empty feeds. See
references/sources.md.

### 4. Blog & changelog (free for most)

**Autodiscover the feed:** `WebFetch` the `/blog` and `/changelog` pages and read the
`<link rel="alternate" type="application/rss+xml">` tag; else try common feed paths.
Parse dated items, keep in-window ones. No feed? Plain `WebFetch` the index page —
titles/links are usually in the server-rendered HTML. Firecrawl only when the page is a
truly empty JS shell.

### 5. Public-company path (only if routed public)

`ticker/name → CIK → filings`. **8-K** = material events (exec changes, M&A, results);
**10-Q** = quarterly priorities + risk factors, straight from the company. Endpoints +
required `User-Agent` header in references/sources.md.

### 6. Synthesize into the report

Rank signals by **impact × recency** (a week-1 launch is stale by now; last week's is a
live trigger). Keep in-window and pre-window signals clearly separated — pre-window items
are context, not "why now".

**Don't claim hiring growth deltas.** ATS APIs return only *currently open* roles, so
filled/closed roles vanish — you cannot honestly say "16 posted this-90 vs 2 prior".
Frame careers as **composition + freshness**: "X of N open roles posted in-window,
concentrated in {departments}", plus standout senior reqs.

## Output Contract

Emit markdown in this shape (a positive recipe — fill every slot):

```
# Last Quarter — {Company}  ·  {YYYY-MM-DD → YYYY-MM-DD}
**Profile:** public/private · {industry} · sources active: {list} ({N of M})

## Top signals — ranked by impact × recency
1. **{signal}** — {one line}.  ({source} · {date}) {url}
2. …

## By category
- **Hiring:** {listed N; X posted in-window; dept concentration}. {ats url}
  - **Tech stack** (mined from JD text, skill-context anchored) — grouped by category,
    ranked by # of JDs; each tool cites an example job. Signals what they run / build.
  - **Stated priorities** — "you'll lead our EU expansion"-type sentences, with the job.
- **Product launches:** … · **Leadership:** … · **Funding/M&A:** …
- **Expansion:** … · **Risk / negative:** {or "none surfaced this window"}

## Coverage & confidence
Sources active: {N of M}. Add a {Firecrawl/Exa/PredictLeads} key to unlock {what}.
Primary-sourced vs aggregator-sourced claims are labeled; unverified items flagged.

{engine `footer` field — passed through verbatim, e.g.:}
---
✅ sources reported back — 2/5 active
└─ careers ✓ 9 · news ✓ 9 · blog ✗ · edgar — · github ✗
---
```

**Rules that make it trustworthy:**
- **Inline source + date on every claim.** Never a lump of sources at the end.
- **Primary sources beat aggregators.** ATS, EDGAR, company blog, press releases first.
  A funding or headcount number from Crunchbase/Sacra/Tracxn/Built In alone is
  **labeled "aggregator, unverified"** — never stated as fact.
- **Negative signals are in scope.** Layoffs, outages, incidents, exec departures, suits
  — surface them. The report is neutral, not a highlight reel.
- **End with the engine's `footer` verbatim.** The coverage line is the trust device —
  it states exactly what was pulled and what was empty. Never omit or paraphrase it.

## Graceful Degradation

Free tier (no keys) must stand alone: careers APIs + Google News RSS + EDGAR + feeds
already produce a real report (verified: even a thin Series-A returns ~13 roles, a
launch, and a positioning shift). Keys deepen, they aren't required. Always end with
"sources active: N of M" and what a key would add — **never return an empty report.**

Paid upgrades: **Firecrawl** (JS-rendered pages), **Exa** (neural date-filtered news),
**Apify** (LinkedIn posts + headcount trend), **PredictLeads** (job/news/tech signals
per domain). Details in references/sources.md.

## Common Mistakes

| Mistake (all seen in unaided baseline) | Fix |
|---|---|
| Scraping the JS careers page, then using an aggregator's job count | Hit the ATS JSON API → exact roles, departments, dates |
| Reporting a fuzzy "~30 roles" | Count from `.jobs[]`; give listed count + in-window posts |
| Stating a funding figure from an aggregator | Require a primary source, else mark unverified |
| Flat snapshot, no trend | Bucket dated items this-90 vs prior-90 |
| Running EDGAR on a private company | Profile first; EDGAR only when a CIK exists |
| Sources lumped at the end | Inline source + date per claim |
| "Insufficient signal" empty report | Free tier still returns ATS + Google News; state what a key adds |
| Accepting a `200` from an ATS as a valid board | Require a non-empty jobs array |
| Including same-name news | Entity-check each article against the target company |
| Reporting careers "this-90 vs prior-90" as growth | ATS shows only open roles (survivorship bias); frame as composition + freshness |
| Inferring "no news" from empty RSS/GDELT | Run a WebSearch pass for funding/leadership/negative before concluding absence |
