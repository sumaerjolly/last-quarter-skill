# last-quarter

**Point your AI agent at a company domain → get a cited report of what they actually did
last quarter.** Product launches, hiring, funding, leadership changes, expansion, incidents,
competitive moves — every claim carries a source URL and a date. Built for SDRs/AEs hunting a
real "why now" for outbound — or point it at a **competitor's** domain and it reads as a
tracking dossier. Inspired by [last30days](https://github.com/mvanhorn/last30days-skill).

```
/last-quarter linear.app
```
```
🗓  last-quarter · Linear (linear.app) · 2026-04-10 → 2026-07-09

  HIRING  ashby · 24 listed, 14 posted in-window · GTM:7, Product:6
  GEO     4 of 14 in-window roles are EMEA-based — possible EMEA expansion.
  NEW-INIT "we're building the product development system for teams and agents" [Staff Eng]
  STACK   TypeScript, GraphQL, React · PostgreSQL, Redis · GCP, Kubernetes · OpenAI
  LAUNCH/BLOG  18 in-window   ·   HN  11   ·   GITHUB  30 releases
  ✅ sources reported back — 6/8 applicable
```

Free out of the box: **no keys, no signup, no `pip install`** — just Python 3.11+ (already on
modern Macs) and any AI agent. Optional self-serve keys make it sharper.

## Install (60 seconds)

**Easiest — let your agent do it.** Paste this into Claude Code, Codex, Cursor, or any
agent with shell access:

> Install the last-quarter skill: clone https://github.com/sumaerjolly/last-quarter-skill
> to a skills folder, read its SKILL.md, and verify it works by running the engine's
> `--diagnose` command.

**Claude Code** — one command:
```bash
git clone https://github.com/sumaerjolly/last-quarter-skill ~/.claude/skills/last-quarter
```
Then in any chat: `/last-quarter stripe.com` — or just ask *"prep me for a call with Stripe."*

**Codex** — clone it, then register it in your `AGENTS.md` so Codex knows when to use it:
```bash
git clone https://github.com/sumaerjolly/last-quarter-skill ~/.codex/skills/last-quarter
echo '- For company research / outbound prep ("what happened at X last quarter"), read and follow ~/.codex/skills/last-quarter/SKILL.md' >> ~/.codex/AGENTS.md
```
Then ask Codex: *"what happened at stripe.com last quarter?"*

**Cursor / Windsurf / any other agent** — clone anywhere and point the agent at `SKILL.md`
(reference it from your rules/`AGENTS.md` file, or paste its path into the chat). The
SKILL.md contains complete instructions: the agent runs the engine and edits the report it
produces.

**Update later:** `git -C <install-path> pull`

<details>
<summary><b>For AI agents installing this</b> (deterministic steps)</summary>

1. `git clone https://github.com/sumaerjolly/last-quarter-skill <skills-dir>/last-quarter`
   — for Claude Code, `<skills-dir>` is `~/.claude/skills`.
2. Verify: `python3 <skills-dir>/last-quarter/engine/last_quarter.py --diagnose`
   — expect `[OK]` rows for ashby/greenhouse/google_news/hackernews/statuspage/sec_edgar/
   github; paid rows show `— no key` (normal).
3. To run: read `<skills-dir>/last-quarter/SKILL.md` and follow it exactly. The engine
   command is `python3 <skills-dir>/last-quarter/engine/last_quarter.py {domain} --emit md`.
4. Optional keys live in `~/.config/last-quarter/.env` (see `.env.example` in the repo).
</details>

## Optional: add keys, get superpowers

The free tier stands alone. Three **self-serve** keys deepen it (no sales calls):

| Key | Unlocks |
|---|---|
| `EXA_API_KEY` | Entity-resolved news — fixes common-word name collisions, real publisher URLs |
| `FIRECRAWL_API_KEY` | Renders JS-only blogs the free tier can't read (cost-capped) |
| `PDL_API_KEY` | **Actual new hires** — named senior joiners + LinkedIn + department rollup |

```bash
mkdir -p ~/.config/last-quarter && cp .env.example ~/.config/last-quarter/.env
# fill in whichever keys you have — missing ones are silently skipped
```
Every run's footer shows exactly what each key spent (`paid: exa 1 call · pdl 20 credits`).

## What it collects

| Signal | Source (free) |
|---|---|
| Open roles, senior/leadership reqs, dept mix, geo expansion | ATS APIs (Ashby/Greenhouse/Lever + board discovery) |
| Tech stack, stated priorities, **new-team initiatives** | Mined from job-description text |
| Launches & product direction | Blog/changelog RSS+HTML, GitHub releases & net-new repos |
| Customer wins | Case-study titles |
| News | Google News + GDELT (entity-filtered) |
| Risk | Status-page incident history |
| Community/discussion | Hacker News |
| Filings (public cos) | SEC EDGAR |
| Website technographics (~65 tools incl. ABM/intent) | Script/header fingerprints |
| Competitive moves (displacement, attacks, comparisons) | Mined across all titles |

Everything also lands in a normalized **`signals[]` JSON array** (typed, dated, cited,
confidence-labeled, ranked) — pipe it into your own enrichment or outbound tooling:
`--emit json`.

## Run it without an agent

The engine is a plain CLI:
```bash
python3 engine/last_quarter.py stripe.com --emit md
```
Flags: `--keywords "what they do"` (needed for common-word names like Ramp/Notion) ·
`--emit compact|json|md` · `--today YYYY-MM-DD` · `--quiet` · `--diagnose`
(troubleshooting: run it and paste the output).

## Design principles

- **Every claim cited** (URL + date) — a wrong signal in a cold email burns the sender.
- **Primary sources over aggregators** — ATS JSON, EDGAR, RSS, status pages; not scraped guesses.
- **Entity-verified** — "Mercury" won't get a defense contractor's filings; "Reflow" won't get
  Reflow Medical's news.
- **Honest degradation** — never a fake-complete report; the footer says exactly what ran,
  what a key would add, and what each paid call cost.

MIT licensed. Not affiliated with any data provider — respect each source's terms.
