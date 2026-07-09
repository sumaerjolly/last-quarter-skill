# last-quarter

**An agent skill: point your AI agent at a company domain → get a cited report of what they
actually did last quarter.** Product launches, hiring, funding, leadership changes, expansion,
incidents, competitive moves — every claim carries a source URL and a date, so an SDR/AE can
pick a real "why now" for outbound. Inspired by
[last30days](https://github.com/mvanhorn/last30days-skill).

Install it in Claude Code (or any agent that reads a `SKILL.md`), then:

```
/last-quarter stripe.com
```

The agent runs a **stdlib Python engine** (no `pip install`, Python 3.11+) that fans out ~9
free sources, then edits the deterministic report the engine produces. Works **free out of the
box** — add optional self-serve API keys and it gets sharper.

## Why

Free careers/news/filings/status data is scattered across a dozen APIs, and generic "research
this company" prompts drift into hallucinated or same-name-collision garbage. `last-quarter`
goes to **structured primary sources** (ATS JSON, SEC EDGAR, RSS, status pages), scores and
ranks the signals, and hands you a report where **every line is cited** — plus a normalized
`signals[]` JSON array so you can pipe it into your own enrichment/outbound tooling.

**Two audiences, one command:** point it at a *prospect* for outbound research, or at a
*competitor's* domain — every signal reads as competitor tracking (they took a rival's
customers, someone launched against them, who they're bracketed with).

## What you get (free tier)

```
🗓  last-quarter · Linear (linear.app)  ·  2026-04-10 → 2026-07-09
    profile: private

  HIRING  ashby · 24 listed, 14 posted in-window · GTM:7, Product:6, Operations:1
  STACK   Languages: TypeScript, GraphQL, React · Data: PostgreSQL, Redis · Cloud: GCP, Kubernetes
  GEO     4 of 14 in-window roles are EMEA-based — possible EMEA expansion.
  NEW-INIT  "we're building the product development system for teams and agents" [Staff Fullstack]
  SITE  Framework: Next.js · Infra: Cloudflare
  LAUNCH/BLOG  18 in-window
  NEWS  ...   RISK/STATUS  ...   HN  ...   GITHUB  ...
  ✅ sources reported back — 6/8 applicable
```

Signal types, all cited: **hiring** (open reqs, dept mix, senior/leadership reqs, geo
expansion), **JD-mined tech stack + stated priorities + new-team initiatives**, **product**
(blog/changelog, GitHub releases, net-new repos), **traction** (customer wins from case
studies), **news**, **risk** (status-page incidents), **HN discussion**, **SEC filings**
(public cos), **observed website technographics** (what's installed on their site), and
**competitive dynamics**.

## Sources

**Free (no keys):** careers (Ashby / Greenhouse / Lever + board discovery) · JD mining ·
Google News + GDELT · blog/changelog (RSS + HTML fallback) · status-page incidents ·
Hacker News · SEC EDGAR · GitHub releases · website technographics (~65 fingerprints).

**Optional paid (self-serve keys — free tier stands alone without them):**

| Key | Unlocks |
|---|---|
| `EXA_API_KEY` | Entity-resolved news (fixes common-word name collisions; real publisher URLs) |
| `FIRECRAWL_API_KEY` | Renders JS-shell blogs the free tier can't read (cost-capped) |
| `PDL_API_KEY` | **Actual new hires** — named senior joiners + LinkedIn + dept rollup |

No key set → that source is silently skipped. The footer's `paid:` line shows exactly what
each key spent per run.

## Install

It's a self-contained Agent Skill: a `SKILL.md` (instructions) + a stdlib engine, no deps.

**Claude Code** — drop it where Claude discovers skills:
```bash
git clone https://github.com/sumaerjolly/last-quarter-skill
ln -s "$PWD/last-quarter-skill" ~/.claude/skills/last-quarter
```
Then in any Claude Code session: `/last-quarter stripe.com` (or "prep me for a call with
Stripe"). Claude reads `SKILL.md`, runs the engine, and writes the report.

**Codex / Cursor / any agent** — clone it and point your agent at `SKILL.md` (e.g. reference
it from `AGENTS.md`, or paste its path). The skill tells the agent exactly how to run the
engine and shape the output.

**Keys are optional.** Put self-serve API keys in `~/.config/last-quarter/.env` (see
`.env.example`); the engine auto-loads them. Real environment variables take precedence. No
keys → the free tier runs, fully.

## Run it directly (no agent)

The engine is a plain CLI too:
```bash
python3 engine/last_quarter.py stripe.com --emit md      # zero config, free tier
```
```
last_quarter.py {domain} [--name "Company"] [--today YYYY-MM-DD] [--keywords "descriptor"]
                [--emit compact|json|md] [--quiet] [--diagnose]
```

- `--emit md` — deterministic ranked report (recommended). `--emit json` — the machine
  interface (`signals[]`). `--emit compact` — quick human scan.
- `--keywords "what they do"` — needed for common-word names (Ramp, Notion, Reflow) so news
  disambiguates.
- `--diagnose` — health-check every integration (support: "run this and paste the output").

## Design principles

- **Every claim cited** (URL + date) — trust is the product; a stale/wrong signal in an email
  gets a rep burned.
- **Primary sources over aggregators** — ATS/EDGAR/RSS, not scraped guesses.
- **Precision over recall** — entity-verified (a company named "Mercury" won't get a defense
  contractor's filings; "Reflow" won't get Reflow Medical's news).
- **Honest degradation** — never an empty report; the footer says exactly what ran, what a key
  would add, and what each paid call cost.

## License

MIT. Not affiliated with any data provider. Respect each source's terms.
