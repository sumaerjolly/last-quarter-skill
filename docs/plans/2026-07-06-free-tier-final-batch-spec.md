# Implementation Spec: Free-Tier Final Batch (4 extractions + 1 GREEN test)

**Date:** 2026-07-06
**For:** the implementing model. Execute exactly; do not re-litigate decisions.
**Repo:** `~/Desktop/fun-projects/random-shit/last-quarter-skill` (own git repo, branch `main`,
remote `github.com/sumaerjolly/last-quarter-skill`, private).

## Context (read first, don't re-derive)

The `last-quarter` engine (`engine/`) is a **stdlib-only Python 3.11** collector: domain in →
structured JSON of trailing-90-day ABM signals out (~8s). An LLM synthesizes a cited report
from the JSON per `SKILL.md`. Non-negotiable house rules:

1. **Stdlib only. No pip installs.** The free tier must run bare.
2. **Precision over recall.** Every extractor that pattern-matches text must have negative
   guards and unit tests for false positives (see `lib/jd_mining.py` for the house style).
3. **Provenance on everything.** Extracted items carry the source item (job/post title + URL).
4. **Zero new network fetches** for items 1–4 below — they extract from responses the engine
   already downloads.
5. **Tests:** `engine/test_engine.py`, run `python3 -m unittest test_engine` from `engine/`.
   Currently 23 pass. Every new extractor gets positive + negative tests.
6. Run everything with `--today 2026-07-06` for deterministic windows.
7. Commit style: see `git log` — imperative subject, body explains what/why, ends with the
   Co-Authored-By line already used in prior commits (match your own model name).

Verification companies (all verified live earlier): `airops.com` (AirOps), `datadoghq.com`
(Datadog), `ramp.com` (Ramp, use `--keywords "fintech OR payments"`), `linear.app` (Linear),
`mybrightwheel.com` (Brightwheel), `notion.so` (Notion).

---

## Task 1 — Geo rollup from careers locations → Expansion signal

**File:** `engine/lib/careers.py`, inside `collect()` (after `in_window` is computed).

`board["jobs"]` items already carry `location` (string or None; Ashby e.g.
`"New York City or San Francisco (Onsite)"`, `"EMEA"`, `"Brazil"`; Greenhouse
`location.name`; Lever `categories.location`).

**Build:** a `geo_rollup` over **in-window** jobs:
- Bucket each job's location into coarse regions via keyword matching (case-insensitive,
  substring): `EMEA` (emea, europe, london, berlin, paris, amsterdam, dublin, germany, uk,
  united kingdom), `APAC` (apac, singapore, sydney, tokyo, india, japan, australia),
  `LATAM` (latam, brazil, mexico, argentina, colombia), `North America` (us, usa, united
  states, new york, san francisco, nyc, boston, austin, seattle, toronto, canada, remote -
  us, north america), `Remote` (bare "remote" with no country qualifier). Unmatched → `Other`.
  Order matters: check specific regions BEFORE the generic "remote" bucket ("Remote - EMEA"
  → EMEA, not Remote).
- Output field on the careers result:
  `"geo_rollup": [["North America", 5], ["EMEA", 3], ...]` (Counter.most_common()).
- **Expansion flag:** if ≥2 in-window roles fall in a non-domestic region AND that region is
  not the majority region, add
  `"geo_note": "N of M in-window roles are {region}-based — possible {region} expansion."`
  Only one note (pick the largest qualifying region); `None` otherwise.

**Compact view** (`engine/last_quarter.py`, in the careers block): if `geo_note`, print a
line `  GEO     {geo_note}` after the STACK line.

**Tests (add `TestGeoRollup`):**
- Jobs in "London", "Berlin", "New York" → EMEA count 2, geo_note mentions EMEA.
- "Remote - EMEA" buckets to EMEA, not Remote.
- All-US jobs → geo_note is None.

**Live check:** `python3 last_quarter.py airops.com --name "AirOps" --today 2026-07-06`
should show a GEO line mentioning EMEA (they have German-speaking EMEA SDR reqs) — IF those
roles are still in-window; if not, verify via the JSON `geo_rollup` field instead and say so.

---

## Task 2 — Customer-win extraction from blog titles → Traction signal

**File:** new `engine/lib/customer_wins.py` + call it from `engine/lib/blog.py::collect()`
over the final `uniq` list (titles + urls already in hand).

Case-study titles name customers. Real examples from our runs:
- "How Angi Built a Longtail Content Strategy that Converts 79% Better" → **Angi**
- "Why Childcare Programs Switch from Playground to Brightwheel" → competitive story
- Common shapes: "How {X} {verb}...", "{X} Customer Story", "Case Study: {X}",
  "{X} + {Brand}", "Why {X} chose {Brand}", "{X}'s journey with ..."

**Build `extract_customer_wins(items: list[dict], brand: str | None) -> list[dict]`:**
- Patterns (anchored, precision-first — match TITLE shapes, not free text):
  - `^How ([A-Z][A-Za-z0-9&.\' -]{2,30}?) (?:built|uses?|used|scaled|grew|achieved|automated|
    saved|increased|reduced|cut|transformed|streamlined|improved|drove|boosted|switched|went)`
  - `^(?:Case Study|Customer Story|Customer Spotlight)[:\-–] ?([A-Z][A-Za-z0-9&.\' -]{2,30})`
  - `([A-Z][A-Za-z0-9&.\' -]{2,30}?) (?:Customer Story|Case Study)$`
  - `^Why ([A-Z][A-Za-z0-9&.\' -]{2,30}?) (?:chose|switched to|picked|moved to|uses)`
- **Guards:**
  - Extracted name must NOT be (case-insensitive) the brand itself, nor start with a
    lowercase word, nor be in a stoplist: `{we, i, you, your, our, the, this, that, it, ai,
    llms, marketers, teams, companies, brands, leaders, one, many, most, top}`.
  - Must be ≤4 words.
  - Dedupe by lowercased name.
- Return `[{"customer": "Angi", "title": <full title>, "url": <post url>, "date": <date>}]`.
- Wire into blog result as `"customer_wins": [...]` (cap 8). Compact view: if any, print
  `  CUSTOMERS  {names, comma-joined}  (from case studies)` in the blog block — add after the
  existing note logic in the blog section of `compact()`.

**Tests (add `TestCustomerWins`):**
- "How Angi Built a Longtail Content Strategy that Converts 79% Better" → Angi.
- "How to Build a Brand Kit That Makes Your Content Sound Like You" → NOTHING ("to" is
  lowercase → guard must reject; this is a real AirOps title that must not false-positive).
- "How AI Changed Marketing" → NOTHING (stoplist).
- "Ramp Customer Story" with brand="Ramp" → NOTHING (self-name).
- "Case Study: Kayak" → Kayak.

**Live check:** AirOps blog should surface Angi (their listing had `angi-customer-story`).

---

## Task 3 — Senior-hire flagging in careers → Leadership signal

**File:** `engine/lib/careers.py`, in `collect()`.

**Build:** scan **in-window** job titles for seniority markers (case-insensitive, word-ish
boundaries): `chief, cto, ceo, cfo, coo, cro, cmo, ciso, vp, vice president, head of,
director, founding, president, general manager, gm,`. Exclusions: `associate director`
counts (fine), but reject when the marker is part of a product-y phrase — practical guard:
title must MATCH `(?i)(?<![a-z])(chief|cto|ceo|cfo|coo|cro|cmo|ciso|vp|vice president|
head of|director|founding|general manager)(?![a-z])` and NOT match `(?i)direct(or)? of
photography|art director` (keep it simple; these are the only realistic traps).

Output on careers result: `"senior_roles": [{"title", "department", "date", "url"}]`
(sorted by date desc, cap 6). Compact: print each as
`  SENIOR  - {date} {title} [{department}]` right after the dept-concentration HIRING line
(before STACK).

**Tests (add to careers-adjacent test class or new `TestSeniorRoles` — note: `collect()`
does network; test the extraction by factoring the senior-scan into a small pure function
`_senior_roles(in_window: list[dict]) -> list[dict]` and unit-testing THAT):**
- "VP of Engineering", "Head of Sales", "Founding Biz Ops Lead", "Director, Product" → all flagged.
- "Sales Development Representative", "Senior Software Engineer" → NOT flagged ("Senior"
  alone is IC-level, deliberately not a marker).

**Live check:** AirOps should flag "Founding Biz Ops Lead"; Datadog should flag several
Director/VP roles.

---

## Task 4 — Net-new repo detection in GitHub → Product-direction signal

**File:** `engine/lib/github.py`, in `collect()`.

The `/orgs/{login}/repos?sort=pushed` response items already include `created_at`, `name`,
`html_url`, `description`, `fork`, `stargazers_count`. **Zero new calls.**

**Build:** from the `repos` list (all 15 fetched, not just the 8 release-scanned):
- `new_repos = [r for r in repos if not r.get("fork") and bucket(r.get("created_at"), window) == "in_window"]`
- Output field: `"new_repos": [{"name", "description" (truncate 90 chars), "created":
  created_at, "url": html_url}]`, sorted newest first.
- If any, append to the existing `note` (or set it if None):
  `"{n} net-new repo(s) created this quarter: {names} — new product/SDK direction."`
- IMPORTANT: `new_repos` presence alone should NOT flip status to "active" if there are no
  releases — but it SHOULD: if `releases` is empty but `new_repos` is non-empty, return
  status "active" with `count: 0`, the new_repos field, and the note (a brand-new repo IS
  signal). Adjust the early-return/status logic accordingly.
- Compact view: in the GITHUB block, after signals, print each new repo as
  `          + NEW REPO {created[:10]} {name} — {description}`. The existing generic loop
  prints `signals`; add the new-repo lines in the same block (guard `v.get("new_repos")`).

**Tests (`TestNewRepos` — factor the filter into a pure function `_new_repos(repos, window)`
so it's testable offline):**
- repo created in-window, fork=False → included.
- fork=True in-window → excluded.
- created before window → excluded.

**Live check:** `python3 last_quarter.py increase.com --name "Increase" --today 2026-07-06`
— wait: Increase's GitHub org will now be domain-verified via org.blog; earlier verification
showed `orgs/Increase` exists. If org.blog doesn't match increase.com the org is refused —
in that case verify with Datadog/Linear instead and report what you saw. Do NOT weaken the
domain-verification to make this pass.

---

## Task 5 — GREEN test the engine-first SKILL.md (validation, no code)

The current `SKILL.md` (engine-first contract) has never been subagent-tested. Protocol:

1. Dispatch ONE general-purpose subagent with exactly this framing:
   > Read and follow this skill EXACTLY as written:
   > /Users/sumaerjolly/Desktop/fun-projects/random-shit/last-quarter-skill/SKILL.md
   > (and its references/sources.md only if the skill directs you to it).
   > Execute the skill for the company **Vanta** (domain: vanta.com). Today's date is
   > 2026-07-06. Produce the final report in the skill's Output Contract format.
   > Afterwards add "SKILL EXECUTION NOTES": (1) did you run the engine or fall back to
   > manual recipes, and the exact command; (2) which JSON fields you used; (3) anything
   > ambiguous or contradictory in SKILL.md; (4) anything you had to improvise.
   (Vanta is deliberately UNSEEN by prior tests and is a common-word name — noisy-news
   handling must show up.)
2. **Pass criteria** — verify in the returned report:
   - Ran `python3 engine/last_quarter.py vanta.com ... --json` (not manual curls).
   - Footer passed through VERBATIM as the report's last block.
   - Per-claim inline citations (no lumped sources section).
   - Respected `noisy` flag / notes (e.g., careers survivorship phrasing, news caveats).
   - No "Trajectory" section (removed from contract); careers framed as composition+freshness.
3. **If any criterion fails:** fix SKILL.md wording (the contract, not the engine) to close
   the specific gap, then re-run ONE more subagent on a different company (ramp.com) to
   confirm. Follow the writing-skills ethos: fix the exact observed failure, don't rewrite
   wholesale.
4. Record results (pass/fail per criterion + fixes made) in
   `docs/brainstorms/2026-07-06-green-test-results.md`.

---

## Definition of done

- [ ] Tasks 1–4 implemented with pure-function extractors + unit tests (target ≥31 tests, all pass)
- [ ] `python3 -m unittest test_engine` green
- [ ] Live spot-checks run for each task (AirOps, Datadog, +as specified); paste key lines
      into the final summary to the user
- [ ] SKILL.md Output Contract updated: Hiring gains "senior roles" + "geo/expansion" lines;
      Product/Traction gains "customer wins (case studies)" + "net-new repos"
- [ ] Task 5 GREEN test executed and results doc written
- [ ] ONE commit for tasks 1–4 (single logical batch: "extract more signal from data already
      fetched"), ONE commit for task 5 doc/SKILL.md fixes if any. Push both to origin main.
- [ ] Update memory file
      `~/.claude/projects/-Users-sumaerjolly-Desktop-fun-projects-random-shit/memory/last-quarter-skill.md`:
      free tier now COMPLETE (final batch: geo rollup, customer wins, senior roles, new repos,
      GREEN-tested contract); next = paid P1 Exa per 2026-07-03-paid-tier-plan.md.

## Explicitly OUT of scope (do not do)

- No new network sources (press/newsroom scan is deliberately deferred; do not add it).
- No paid integrations (Exa/PDL/Firecrawl) — parked in 2026-07-03-paid-tier-plan.md.
- Do not weaken any trust guard (domain verification, contamination guard, common-word
  filter) to make a live check pass — report the discrepancy instead.
- Do not refactor the registry or reorganize files beyond what the tasks require.
