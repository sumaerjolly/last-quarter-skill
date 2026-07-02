# Plan: New-Hires Signal (paid tier)

**Date:** 2026-07-02
**Status:** Decision captured — PDL chosen as first integration. Discuss before building.
**Related:** free-source expansion is separate (2026-07-02-free-sources-expansion-brainstorm.md).

---

## Decision

**Use PeopleDataLabs (PDL) Person Search as the first new-hires source.** Prototype the
signal on PDL; upgrade to Crustdata later if it earns its place.

**Why PDL first:** self-serve, **public pricing + 500 free trial credits**, official
Python/Node SDK, and it can run our exact query — `job_company_website = {domain} AND
job_start_date >= {date}` — returning name, title, `job_title_levels` (seniority),
`job_title_role` (department), start date, and `linkedin_url`. Cheapest/fastest way to
prove the signal lands before paying for anything sales-gated.

## What the signal is

New line under **Hiring**, distinct from open roles (which stay free via ATS):

- **New hires (realized), last ~90 days:**
  - **Senior/leadership hires → named individually:** name, role, start month, LinkedIn,
    with a source + confidence flag. *(e.g. "Jane Doe → VP Eng, joined May 2026")*
  - **Everyone else → department rollup:** *"Sales +6, Eng +3."*
- **Open roles (intent)** and **new hires (realized)** are labeled separately — different
  stories (forward intent vs realized growth + real people to reference).

## Constraints / honest caveats

- **Month precision only** — no "joined 2026-05-12". Day-dated *named exec* hires stay the
  job of the **free exec-hire-via-news** path (event-verb filter: appoints/names/hires).
- **PDL freshness is the weak spot** — monthly rebuild + `job_last_changed` = propagation,
  not the actual switch (weeks-to-months lag). Mitigations: widen window to ~120 days,
  dedupe across runs, label the line **"recent joiners (approx.)"**. Do NOT present as
  real-time or complete.
- **Paid/opt-in tier only** — runs only when a PDL key is present. Free tier never depends
  on it; the coverage footer shows it as an available-with-key source.
- **Cost control** — Search bills 1 credit per returned record (~$0.20–0.28). Cap results
  per run; only fire on explicit opt-in / when the free hiring signal is thin.

## Upgrade path (for the "then we talk" conversation)

- **Crustdata = production upgrade.** Purpose-built `recently_changed_jobs` (90d) filter +
  `/company/enrich` **headcount growth % QoQ/YoY by department** (the survivorship-free
  hiring *trajectory* we cut) + Watcher webhooks (freshness within hours). Frictions:
  sales-gated pricing, no clear free trial, freshest data is enterprise-gated (its cheap
  in-DB tier is monthly like PDL). Move here once the signal proves out.
- **Sumble = only if we separately want tech-stack/technographics** (two-for-one via the
  Printing Press credit-aware CLI/MCP wrapper). Not the pick for new-hires alone.
- **Flagged standalone win:** **headcount-growth-QoQ** (Crustdata `/company/enrich`) is a
  killer single datapoint — arguably the first paid thing to add, independent of full
  new-hire rosters.

## Integration approach

- Paid sources integrate as **opt-in modules**, keeping the free Python engine
  dependency-free. Prefer **MCP from the agent layer** (PDL/Crustdata/Sumble all expose
  MCP) over wiring REST into the engine, OR a thin PDL-SDK collector gated on the key.
- Fits the planned **source registry** (`tier: paid, requires_key: PDL_API_KEY,
  applies_if: has_key`).

## Research basis (2026-07-02, three parallel scoping agents)

- **PDL:** ✅ server-side `job_start_date` range + company-domain filter; all fields
  present; ~$0.20–0.28/record; ⚠️ monthly/batch freshness. Chosen for prototype.
- **Sumble:** daily re-match + tech-stack graph; ❌ no date-range filter (sort+window),
  month precision; self-serve + Printing Press wrapper.
- **Crustdata:** ✅ best capability + freshness (`recently_changed_jobs`, headcount growth
  QoQ, Watcher webhooks); ❌ sales-gated, freshest tier enterprise-only. Production upgrade.

## Open (for discussion)

1. Prototype scope — just the dept rollup + named senior hires, or also pull headcount
   total from PDL now?
2. When to trigger PDL — always (if key present) vs only when ATS hiring signal is thin?
3. Timing of the Crustdata conversation — after PDL MVP, or scope pricing in parallel now?
