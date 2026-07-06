# Paid Tier — Consolidated Plan

**Date:** 2026-07-03
**Status:** Single source of truth for paid sources (supersedes the paid bits scattered in
the new-hires plan, the free-source brainstorm, SKILL.md, and references/sources.md).

---

## Principle

Free tier stands alone (7 sources + JD mining). Paid = **opt-in "add keys" enrichment**,
integrated via **MCP from the agent layer** or thin key-gated collectors, keeping the
pure-Python free engine dependency-free. Paid runs should be **opt-in / escalation-only**
(when the free signal is thin), with cost caps — Apify/PDL/Crustdata cost real money.

## What free JD mining changed

We now get **technographics (tech stack) for FREE** from JD mining. That **demotes Sumble**
(its main draw was tech-stack). Paid focus shifts to signals free genuinely can't get:
fresh new-hire rosters, entity-resolved news, and rendered-page diffs.

---

## The paid sources, by the job they do

### 1. New hires + headcount trajectory — the biggest paid win
Fixes the hiring *trajectory* we cut (ATS survivorship bias) with real joiners + headcount.
- **PeopleDataLabs (PDL)** — START HERE (prototype). `job_company_website + job_start_date`
  filter; name/title/seniority/dept/LinkedIn/start-month. Self-serve, 500 free credits,
  Python SDK, ~$0.20–0.28/record. Weakness: monthly-batch freshness (widen window ~120d,
  label "approx.").
- **Crustdata** — PRODUCTION upgrade. Native `recently_changed_jobs` (90d) + `/company/enrich`
  **headcount growth QoQ/by-dept** + Watcher webhooks (fresh). Sales-gated, freshest tier
  enterprise. **Headcount-growth-QoQ = flagged killer STANDALONE datapoint** (one cheap call
  gives the clean trajectory ATS can't).
- **Sumble** — DEPRIORITIZED (tech-stack now free). Only if we want its deeper org/tech graph.
  Has a Printing Press credit-aware CLI/MCP wrapper.
- Decision: **PDL prototype → Crustdata production.** (Detail: new-hires-signal-plan.md.)

### 2. News that free can't disambiguate
- **Exa** — neural, date-filtered, entity-resolved company news. Fixes the common-word
  collision free Google News chokes on (Increase, Ramp, Linear). Directly upgrades a core
  category. High priority.

### 3. JS-rendered pages + positioning/pricing diff
- **Firecrawl** — renders JS that free WebFetch can't:
  - JS careers pages (custom/Workday ATS with no public API)
  - true JS-shell blogs (rare; most are server-rendered and handled free)
  - JS status widgets (non-Statuspage providers, e.g. Increase)
  - **Wayback positioning/pricing diff** (tested: needs render): CDX finds the ~90d-old
    snapshot → Firecrawl renders archived-old + current → structured `/extract`
    `{tagline, plans:[{name,price}]}` on both → diff → "repositioned X→Y / added Enterprise
    tier / Starter $16→$20". Risk: Wayback sometimes fails to archive the JS bundle → shell
    even in a browser; fall back to archived SSR meta (title/og) for positioning-lite.

### 4. Social / reviews (fragile, ToS-gray, escalation-only) — via Apify actors
- **LinkedIn** — company posts, headcount trend, new senior hires (overlaps Crustdata;
  scrape-based/fragile).
- **Twitter/X** — company + exec activity, launch amplification.
- **Trustpilot / G2** — review volume + rating trend + themes = customer sentiment/health.
- **Glassdoor** — employee sentiment (risk/morale).

## Integration layer
- **Printing Press** (mvanhorn, last30days author) — credit-aware CLI + MCP wrappers with
  cost-estimate/budget guardrails. Confirmed to wrap **Sumble**; does NOT wrap Crustdata.
  Candidate uniform paid layer IF it covers the providers we pick.
- Otherwise integrate each via its own **MCP** (PDL / Crustdata / Sumble / Firecrawl / Exa
  all expose MCP) from the agent layer — keeps the free Python engine dependency-free.

## Recommended priority
- **P1 — Exa (news fix) + PDL (new-hires prototype).** Both upgrade core categories; cheapest
  to validate (self-serve + free trials).
- **P2 — Firecrawl.** Unlocks JS careers/status pages + the Wayback positioning/pricing diff.
- **P3 — Crustdata.** Headcount-QoQ standalone + production new-hires.
- **P4 — Apify social/reviews.** Nice-to-have, fragile; escalation-only.

## Open decisions
1. **Escalation model:** paid default-on when key present, opt-in per run, or only-when-free-
   thin? (Lean: opt-in / escalation-only + cost caps.)
2. **Integration:** Printing Press uniform layer vs per-provider MCP.
3. **PDL plan's 3 open questions** (prototype scope, trigger logic, Crustdata timing) still open.

## Rejected (tested, not paid-worthy either)
- **Wikidata** (free) — no coverage for private cos. **Podcasts** (free) — ~50% exec miss +
  needs an exec-name source. **Wayback rich diff on FREE** — needs Firecrawl (moved to §3).
