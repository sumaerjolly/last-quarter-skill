# Implementation Spec: Pre-launch Batch (ranking, --emit md, progress, spend, paths, diagnose)

**Date:** 2026-07-07
**For:** the implementing model (Opus). Execute exactly; decisions are made — do not re-litigate.
**Repo:** `~/Desktop/fun-projects/random-shit/last-quarter-skill` (own git repo, `main`,
private remote `github.com/sumaerjolly/last-quarter-skill`).

## Context (read once, don't re-derive)

`engine/` is a stdlib-only Python 3.11 collector: domain in → JSON of trailing-90-day ABM
signals (~10-20s). 8 free sources + 3 paid key-gated collectors (Exa news, Firecrawl blog
escalation, PDL new-hires) already built and live-verified. A top-level normalized
`signals[]` array (`{type, category, claim, date, url, source, confidence}`) is the machine
interface, currently sorted by date only. Keys auto-load from `.env` via `lib/config.load_env()`
(repo `.env` is gitignored and holds real keys — NEVER stage or print it).

House rules (unchanged from prior specs, all enforced):
1. **Stdlib only, no pip.** 2. **Precision + negative guards + provenance** (see
   `lib/jd_mining.py` house style). 3. **Hermetic tests** — `python3 -m unittest test_engine`
   from `engine/` currently ~53 pass with NO network and NO keys; keep it that way (paid
   collectors must stay dormant in tests). 4. **`--today 2026-07-07`** on every live run for
   deterministic windows. 5. **Never weaken a trust guard to make a check pass** — report
   discrepancies instead. 6. Commit style: match `git log` (imperative subject, why-rich body,
   Co-Authored-By trailer with your model name).
7. **NEW — stdout purity:** stdout carries ONLY the emitted artifact (json/md/compact);
   all progress/diagnostics go to **stderr**. People will pipe this.
8. **Don't burn paid credits in tests.** Live checks below list the exact allowed paid runs.

Execution order: **Task 1 → 2 → 3 → 4 → 5 → 6** (1 feeds 2; 6 is deferrable — if anything
runs long, ship 1–5 and leave 6 with a TODO note in the plan doc).

---

## Task 1 — Coarse signal ranking (feeds --emit md)

**File:** `engine/lib/signals.py`. Add a `score` field to every record and sort `signals[]`
by it. This is a deliberately **coarse floor** — a sane default ordering so the md mode never
puts a fresh blog post above a funding event. It must not pretend to be smart.

- `score = TYPE_WEIGHT × recency × confidence_mult`, rounded to 2dp, added to each record.
- `TYPE_WEIGHT` (coarse tiers, module-level dict — keep EXACTLY this coarse):
  - **5:** `new_hire`, `senior_hire_req`, `new_initiative`, `customer_win`,
    `displacement_win`, `competitor_attack`
  - **4:** `geo_expansion`, `new_repo`, `incident`, `sec_filing`, `new_hires_rollup`,
    `comparison`
  - **3:** `news`, `stated_priority`
  - **2:** `blog_post`, `open_roles`, `hn_discussion`, `tech_stack`, `release`
  - **1:** `data_caveat` (and any unknown type → 2)
- **News event boost:** a generic `news` item whose claim matches a funding/M&A/exec event
  gets weight **5**. Reuse/adapt the event verbs already in `lib/news.py::_EVENT` but
  restrict to the high-stakes subset: `raise[sd]?|raising|funding|series [a-e]|valuation|
  acqui|merg|appoint|names? new|joins as|steps down|resign|layoff|ipo`. Compile once in
  signals.py; do NOT loosen `news._EVENT` itself.
- **Recency decay** — deterministic, measured against `window["end"]` (NEVER
  `date.today()`): age ≤14d → 1.0; ≤30d → 0.8; ≤60d → 0.6; else 0.4; **undated → 0.5**.
- **Confidence multiplier:** `primary` 1.0 · `unverified` 0.8 · `aggregator` 0.7 · `low` 0.4.
- Sort: `score` desc, then `date` desc (undated last within equal score).

**Tests (extend `TestSignals`):** (a) a 40-day-old `new_hire` (primary) outranks a 2-day-old
`blog_post`; (b) a `low`-confidence news item never outranks a `primary` signal of weight ≥4;
(c) funding-verb news gets the boost ("Acme raises $25M Series B" scores above plain news);
(d) every record still has the uniform key set + `score`; (e) determinism: same input →
identical scores (no wall-clock reads).

---

## Task 2 — `--emit md`: deterministic report skeleton

**Files:** new `engine/lib/render_md.py` + CLI wiring in `engine/last_quarter.py`.

**CLI:** add `--emit {compact,json,md}` (default `compact`). Keep `--json` working as an
alias for `--emit json` (back-compat; don't break existing docs/tests).

**`render_md(report) -> str`** — renders the Output Contract shape (see SKILL.md) purely
from the JSON. This is the FLOOR: an LLM may polish/prune it, but a user with no LLM gets a
complete, honest report. Structure, in order:

1. `# Last Quarter — {name} · {window.start} → {window.end}`
2. `**Profile:** {public TICKER|private|unknown (SEC lookup failed)} · sources active: {list} ({footer counts})`
3. `## Top signals` — the **top 8 by score**, EXCLUDING types `tech_stack`, `open_roles`,
   `data_caveat` (those live in By-category). Each: `N. **{claim}** ({source} · {date})` and
   the url on the same line as a markdown link on the date-source parens if url present.
   For `confidence` of `low`: append ` ⚠ entity-check` verbatim.
4. `## By category` — the existing contract's category bullets, driven by the per-source
   dicts (NOT signals[]): Hiring line (+senior roles, geo_note, STACK by category,
   priorities, initiatives), Traction (customer_wins or stated absence), Product direction
   (new_repos or absence), Leadership/Funding ("none surfaced in-window" when absent —
   copy the phrasing rules from SKILL.md's Output Contract), Risk (status incidents or
   "none surfaced"), Competitive (competitive-category signals or omit section).
5. `## Coverage & confidence` — sources active count; EVERY non-null per-source `note`
   rendered as a bullet (survivorship caveat, noisy-news warning, migration-smell,
   Firecrawl dates-unavailable, PDL approx.) — these caveats are the trust posture, they
   MUST survive rendering; plus one "add keys" hint line listing the paid keys NOT set.
6. The engine `footer` **verbatim**, last.

News citations follow the SKILL.md rule: `{claim} — {outlet} · {date}` where outlet comes
from the signal's `source` suffix (`news/TechCrunch` → `TechCrunch`); the opaque link is the
click target only.

**Tests (new `TestRenderMd`, fixture-driven — no network):** (a) footer appears verbatim as
the final block; (b) first Top-signal is the highest-score eligible signal; (c) excluded
types don't appear in Top signals; (d) a source `note` (e.g. survivorship) appears in
Coverage; (e) `low`-confidence items carry the `⚠ entity-check` marker; (f) stdout-purity:
`render_md` returns a string with no ANSI codes.

**SKILL.md update:** in "How to Run", document `--emit md` as the recommended base — the
LLM's job becomes: run engine with `--emit md`, then EDIT the skeleton (prune entity-check
⚠ items after checking them, tighten prose, re-rank within reason) rather than composing
from raw JSON. JSON stays the machine interface. Keep the existing laws (footer verbatim,
citations inline) — they now apply to the edited skeleton.

---

## Task 3 — Progress lines (stderr)

**File:** `engine/last_quarter.py::run()`.

- On start, print to **stderr**: `last-quarter · {name} ({domain}) · {start} → {end}`.
- Switch the executor loop to `concurrent.futures.as_completed` and, as each source lands,
  print one stderr line: `  ✓ careers (9 in-window)` / `  ✗ blog (empty)` / `  ⚠ news (error)`
  / `  — edgar (skipped)`; include count when status==active (same count logic as footer).
- Add `--quiet` flag to suppress all stderr progress. `--emit json|md` output on stdout must
  remain byte-identical with/without progress (verify by eye in live check).
- Keep the per-future timeout behavior identical (as_completed with per-future
  `.result(timeout=...)` semantics — total budget may be enforced via as_completed's
  timeout arg + handling remaining unfinished keys as error results, matching current
  behavior of marking them `status:error`).

No unit tests required beyond suite still passing; correctness shown in live checks.

---

## Task 4 — Paid-spend line in the footer

**Files:** `engine/last_quarter.py::build_footer` (+ collectors already expose usage).

- Standardize: exa result gains `"calls": 1`; blog already has `firecrawl_credits`; pdl
  already has `credits_used`.
- When ANY paid source ran (status not in {skipped}, key was present), append a THIRD line
  inside the footer block, before the closing `---`:
  `└─ paid: exa 1 call · firecrawl 1 credit · pdl 20 credits`
  Only list paid sources that actually ran; omit the line entirely when none did (free-only
  runs keep today's 2-line footer exactly).
- Update `TestFooter` for both shapes (with and without the paid line), and ensure SKILL.md's
  footer example mentions the optional paid line.

---

## Task 5 — Free listing-path coverage (/resources, /customers, /case-studies)

**File:** `engine/lib/blog.py`.

- `_html_listing` pages tuple: `("/blog", "/changelog", "/updates", "/news", "/resources",
  "/customers", "/case-studies")`.
- `_POST_LINK` pattern: extend the path group to
  `blog|changelog|news|updates|posts|resources|customers|case-stud\w+|stories|insights`.
- The free path still requires a machine-readable date per post (`_post_meta`), so undated
  marketing pages are naturally dropped — that guard stays. `_HTML_FALLBACK_CAP` stays 20.
- **Tests:** `_POST_LINK` matches `/resources/some-guide`, `/case-studies/acme`,
  `/customers/acme-story`; still rejects `/pricing` and `/about`.

---

## Task 6 — `--diagnose` (DEFERRABLE — ship 1-5 first if time is a concern)

**Files:** new `engine/lib/diagnose.py` + CLI flag in `last_quarter.py`.

Purpose: one-command health check across all 11 live integrations so OSS support becomes
"run `--diagnose` and paste the output".

- Probes (each: name → OK/FAIL + one-line detail; ~10s total; sequential is fine):
  - ashby: `job-board/airops` returns ≥1 job
  - greenhouse: `boards/datadog/jobs` returns ≥1 job
  - lever: `postings/brightwheel` returns 200 (empty [] counts as OK — reachable)
  - google_news: RSS for "Datadog" parses ≥1 item
  - gdelt: SKIP by default (rate-limited); print `— skipped (throttled API)`
  - hackernews: Algolia query returns 200 JSON
  - statuspage: `githubstatus.com/history.rss` parses
  - sec: `company_tickers.json` loads AND one CIK-scoped search returns 200
  - github: `orgs/datadog` 200 (note remaining rate-limit from `X-RateLimit-Remaining`
    header if easily available via urllib; else just OK)
  - exa: if key set → 1 search with `numResults: 1` (1 minimal call); else `— no key`
  - firecrawl: if key set → print `key set (not probed — costs a credit)`; else `— no key`
  - pdl: if key set → search with `size: 1` (≤1 credit); else `— no key`
- Output to stdout (it IS the artifact in this mode), aligned table, exit code 0 always
  (it's a report, not a gate).
- No unit tests needed (network tool by nature); guard: `--diagnose` ignores domain arg
  (make domain optional when the flag is present).

---

## Live checks (paste key lines into the final summary)

1. `python3 last_quarter.py reflow.ai --name "Reflow" --today 2026-07-07 --emit md` —
   confirm: progress on stderr, clean md on stdout, Top signals ordered sensibly (careers/
   senior/initiative items above generic news), Exa noisy note + ⚠ markers present, footer
   verbatim with paid line (exa ran; pdl will spend ≤20 credits — acceptable, count it).
2. Same command with `--quiet 2>/dev/null | head -30` — stdout unchanged.
3. `python3 last_quarter.py datadoghq.com --name "Datadog" --today 2026-07-07 --emit md`
   (full 7-source + 3-paid run; ONE run only) — confirm By-category sections + paid spend
   line `pdl 20 credits`.
4. Free-only regression: `env -i PATH=$PATH python3 last_quarter.py linear.app --name
   "Linear" --today 2026-07-07 --emit md` — wait: `env -i` would still let config.load_env
   read ./.env; instead run with `LAST_QUARTER_ENV=/dev/null` AND temporarily ensure the
   loader honors an explicit-but-empty file by adding, if needed, the rule "if
   $LAST_QUARTER_ENV is set, ONLY that file is read". Implement that rule in config.py (it
   makes the free-only test possible and is the correct override semantics). Confirm footer
   has NO paid line and paid sources show `—`.
5. If Task 6 shipped: `python3 last_quarter.py --diagnose` output.

## Definition of done

- [ ] Tasks 1–5 implemented per spec (6 if time allows), tests extended (~+12, all pass
      **hermetically** — no network, no keys)
- [ ] Live checks 1–4 run and quoted (respect the paid-credit budget: ≤2 PDL runs total)
- [ ] SKILL.md updated: `--emit md` flow, paid footer line, `--quiet`, key-override rule
- [ ] `.env` never staged (verify `git status` before each commit)
- [ ] Commits: one per task or two logical batches; push to origin main
- [ ] Update memory file
      `~/.claude/projects/-Users-sumaerjolly-Desktop-fun-projects-random-shit/memory/last-quarter-skill.md`:
      pre-launch batch shipped (ranked signals[], --emit md skeleton, stderr progress,
      paid-spend footer, listing paths, [diagnose]); next = Phase B packaging/publish;
      Apify/Twitter deferred to v1.1.

## Out of scope (do NOT do)

- No Apify/Twitter collector (deferred to v1.1 by decision).
- No new free sources beyond the Task-5 path additions; no press/newsroom collector.
- No delta mode, no implication table, no list mode (all previously rejected).
- No Phase B packaging (frontmatter/install/README) — that's the next batch.
- Do not modify entity-verification guards, cost caps, or the confidence taxonomy.
