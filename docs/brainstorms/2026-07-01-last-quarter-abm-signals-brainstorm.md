# Brainstorm: Last Quarter — ABM Signal Skill

**Date:** 2026-07-01
**Status:** Brainstorm complete → ready for `/ce:plan`
**Inspired by:** [last30days-skill](https://github.com/mvanhorn/last30days-skill)

---

## What We're Building

A `/last-quarter` skill for GTM teams. An SDR or AE types in **one company domain**
(e.g. `mybrightwheel.com`) and gets back a **neutral signal report** of what the
company *did* over the **trailing 90 days** — so a run on 2026-07-01 covers roughly
**April–June 2026**. Output is **markdown, rendered inline to the agent** (no external
surface).

It is NOT a sentiment/"what people say" tool (that's what last30days does). It is a
**trigger-event / ABM intelligence** tool: what the company is *doing*, evidenced and
dated, so the rep can decide the "why now" for outreach themselves.

**Core principle (borrowed from last30days):** genuinely useful on the **free tier**
(no API keys), and "add your keys → it becomes awesome." Graceful degradation with an
honest "N sources active" style banner.

**Scope guardrails (decided):**
- **Single company only.** No list/batch mode. Built for the individual SDR/AE.
- **Neutral report.** We surface the signals; the rep supplies their own company
  details and figures out the angle. We do NOT auto-generate seller-specific pitches.

---

## Why This Approach

The whole value is **trust for outbound**. The failure mode is a plausible-but-
hallucinated signal a rep pastes into an email and gets burned on. So the spine is:

> **Every claim carries a source URL + a date, or it doesn't ship.**

Provenance and recency matter more here than in sentiment research. We synthesize into
a readable report, but never at the cost of a citation.

We mirror the **last30days engine architecture**: a core script with one module per
source, graceful degradation on missing keys, snapshot storage for quarter-over-quarter
comparison, and a watchlist path for recurring runs.

---

## Signal Taxonomy (the real product)

"Priorities / launches / hires / issues / funding" is too fuzzy to build against. We use
the proven trigger-event taxonomy, and each type gets its own detector:

1. **Hiring signals** — richest *free* source. Roles + counts + departments = where
   budget/initiative is moving. (e.g. "12 AI-engineer reqs" / "new Head of RevOps").
2. **Leadership changes** — new exec = new mandate + reshuffled budget. Highest-
   converting trigger in sales.
3. **Product launches** — changelog + blog = stated strategic priorities.
4. **Funding / M&A** — budget available + growth pressure.
5. **Expansion** — new market, office, pricing tier, positioning shift (homepage diff).
6. **Negative signals** — layoffs, outages, security incidents, lawsuits, exec
   departures. Half the value: risk flag for CS, opening for cost-savers, or a
   "don't email them this week" filter. We surface these too — the report is neutral,
   not a highlight reel.

---

## Source Tiers (honest about "free")

**Free tier — genuinely useful, no keys:**
- **Careers = the goldmine, and it's structured JSON.** Greenhouse
  (`boards-api.greenhouse.io/v1/boards/{co}/jobs`), Lever
  (`api.lever.co/v0/postings/{co}`), Ashby. Public, unauthenticated. Job *deltas*
  quarter-over-quarter are the strongest free signal.
- **News:** GDELT (genuinely free, global), Google News RSS, HN Algolia API. (Most
  "news APIs" people cite are not actually free — we use these three and don't pretend.)
- **Public companies:** SEC EDGAR (free) — 8-K = exec/funding events, 10-Q risk factors
  = stated priorities from the source.
- **Blog / changelog:** RSS *where it exists*; otherwise needs a scraper (paid tier).
- **GitHub releases** for dev-tool targets.

**Paid tier — "add keys → awesome":**
- **Firecrawl** — scrape changelog/careers/blog that lack clean feeds. (Available here.)
- **Exa** — neural, date-filtered "what happened at X" search. Strong fit. (Available.)
- **Apify** — LinkedIn company posts + headcount trend.
- **PredictLeads** — purpose-built: job openings + news events + technology + connection
  signals per company. The premium centerpiece. (Available via Deepline.)
- **Crustdata / TheirStack** — headcount + tech-stack trend.

Tiering: careers + GDELT + EDGAR + RSS (free) → Firecrawl + Exa (mid) →
PredictLeads / Apify / Crustdata (premium).

---

## The 5 Upgrades (better than a clone)

1. **Trajectory computed live (this-90 vs prior-90).** No stored snapshot required —
   we date-bucket the time-stamped sources (news, RSS, GitHub releases, EDGAR filings,
   careers postings by created/updated date) and compute the delta *within a single
   run*. "Hiring accelerated," "launch cadence picked up" is derivable on the **first
   run, for every company, with zero history.** Point-in-time-only numbers (total
   headcount today, which roles were open 90 days ago) can't be reconstructed
   retroactively — those get an **optional local cache** that only pays off if the same
   user re-runs the same company later. Bonus, not a v1 dependency.
2. **Synthesis pass with confidence.** One LLM step over raw signals →
   *"#1 priority this quarter appears to be embedded finance — evidence: 8 hires,
   2 launches, 1 acquisition. Confidence: high."* The "so what," with receipts.
3. **Recency-weighted ranking.** Rank signals by impact × recency so the top of the
   report is always emailable *today* (a week-1 launch is stale by quarter-end).
4. **Honest graceful degradation.** Free run on a thin company returns real signal +
   "add a Firecrawl key to unlock changelog/news depth" — never an empty report.
5. **Provenance on every line.** Source URL + date per claim; nothing ships uncited.

---

## Test Matrix (design against a spectrum)

The pipeline breaks in different places per target. Design against all four:

| Target | Type | Stress-tests | Role |
|---|---|---|---|
| **Linear** (linear.app) | Series C dev-tool | Ashby careers, clean changelog RSS, GitHub releases, moderate news | **Golden happy path** — proves the ceiling |
| **Datadog** (datadoghq.com) | Public dev-infra | SEC EDGAR (8-K/10-Q), earnings, GitHub, high news volume | **Public-company path** (filings + earnings) |
| **Brightwheel** (mybrightwheel.com) | Private vertical SaaS (childcare) | Greenhouse careers, blog launches, *no* GitHub, moderate news | **Representative mid-market** — the realistic SDR target |
| **AirOps** (airops.com) | Series A AI-native | Sparse traditional news, AI-ecosystem buzz, small footprint, Ashby/Lever careers | **The floor** — graceful degradation, "hot but small" |

**The two that matter most:** Linear proves the ceiling; **AirOps proves the floor.**
The floor is the real risk — ~80% of actual ABM targets look like AirOps/Brightwheel,
not Datadog. If the free tier returns "insufficient signal" there, the skill fails its
main user.

*(Stripe deliberately excluded from the core set — it's the news-firehose / dedup
stress test, useful later for hardening, but an outlier, not a representative query.)*

---

## Key Decisions

- **Single company, no list mode** — built for the individual SDR/AE.
- **Neutral report** — surface signals; rep supplies their own pitch angle.
- **Free tier must stand alone** — keys deepen, they aren't required.
- **Every claim cited (URL + date)** — non-negotiable, trust is the product.
- **Trailing 90 days** — run on 2026-07-01 → ~Apr–Jun 2026; exact window in header.
- **Output = markdown inline to the agent** — no `tv` / external surface in v1.
- **Trajectory is a live in-run computation, not a snapshot dependency** — works on
  first run for every company; optional local cache only for point-in-time metrics.
- **Mirror last30days architecture** — per-source modules, graceful degradation.
- **Design against the 4-company spectrum above**, prioritizing the AirOps floor.

---

## Resolved Questions

1. **Window** → **Trailing 90 days** (not calendar quarter). Exact window printed in the
   report header.
2. **Output surface** → **Markdown, rendered inline to the agent.** No `tv` / external
   surface in v1.
3. **Trajectory** → **Live in-run computation** (this-90 vs prior-90 via date-bucketing
   time-stamped sources). No stored snapshot required; works on first run for every
   company. Optional local cache is a v2 nicety, only for point-in-time metrics that
   can't be reconstructed retroactively (total headcount, roles open 90 days ago).

## Open Questions

_None blocking. Ready for `/ce:plan`._

---

## Next

Run `/ce:plan` to turn this into an implementation plan (source modules, degradation
logic, synthesis prompt, report format, test harness against the 4 targets).
