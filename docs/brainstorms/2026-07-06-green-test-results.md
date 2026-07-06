# GREEN Test Results: engine-first SKILL.md

**Date:** 2026-07-06
**Test:** one general-purpose subagent followed `SKILL.md` end-to-end for **Vanta**
(vanta.com), an UNSEEN + common-word-name company. Today = 2026-07-06.

## Verdict: PASS (all 5 criteria)

| Criterion | Result |
|---|---|
| Ran the engine, not manual curls | ✅ `python3 engine/last_quarter.py vanta.com --name "Vanta" --today 2026-07-06 --json` |
| Footer passed through VERBATIM as last block | ✅ |
| Per-claim inline citations (no lumped sources) | ✅ every signal has source + date + URL |
| Respected `noisy` / notes / survivorship phrasing | ✅ + hand-entity-checked 47 news hits |
| No "Trajectory" section; careers = composition+freshness | ✅ |

The report itself was strong and emailable: new CFO (John McCauley), $300M ARR, TPRM-agent
launch, FedRAMP 20x, 74/106 roles in-window (Revenue-heavy), EMEA+APJ expansion, an incident
cluster (Risk), and a Rippling-competitor mention. All four new extractions exercised:
`senior_roles` (6 named), `geo_note` (EMEA+APJ), `customer_wins` (empty — JS-shell blog),
`new_repos` (empty — no domain-owned org). The two empties were correctly reported as
coverage gaps with the Firecrawl unlock, not omitted.

## Gaps the test found (SKILL.md doc drift, NOT engine bugs) — all fixed

1. **`status` + `hackernews` were undocumented in the Output Contract / footer / source list.**
   Engine returns 7 sources; the contract only named 5, so the agent had to improvise where
   to slot incidents and HN posts. → Added both to the source list, Output Contract (Risk ←
   status; Discussion/community ← hackernews), and the footer example.
2. **Stale footer example** ("2/5 active", 5 sources) vs the engine's actual "N/M applicable"
   over 7 sources. → Updated the example to the real 7-source, "applicable"-denominator form.
3. **`noisy:false` misread as "entity-clean."** The agent correctly hand-filtered ~6 same-name
   collisions (a metal band, a peptide-pharma "Vanta", a Show-HN notes app) despite
   `noisy:false`. → SKILL.md now states explicitly: `noisy` only reflects the common-word
   filter; entity-check every headline regardless.

## Known deferred issue reconfirmed (not fixed here)
- **Google News citation URLs are opaque `news.google.com/rss/articles/CBMi…` redirect blobs**
  — long, ugly, un-eyeballable. Engine-level fix (resolve/clean the redirect) tracked as a
  separate item; out of scope for this batch.

## Re-run decision
The spec says re-run on ramp.com only if a criterion fails. None failed. The three fixes are
additive documentation (naming slots the agent already filled correctly by improvising), so
they cannot regress a passing run. Re-run skipped intentionally.
