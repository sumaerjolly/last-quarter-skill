# last-quarter engine

Stdlib-only Python (3.11+). **No `pip install`** — the free tier just runs.

```bash
python3 last_quarter.py increase.com --name "Increase" --today 2026-07-01 --json
python3 last_quarter.py datadoghq.com --name "Datadog"                 # compact view
python3 last_quarter.py ramp.com --keywords "fintech OR banking"       # common-word name
```

Fans out every source concurrently and emits structured JSON (or a `compact` summary) in
~7s. A synthesis layer (the skill / an LLM) turns the JSON into the final report.

## Flags
- `--name` — display/search name (default: derived from domain).
- `--today YYYY-MM-DD` — pin the trailing-90-day window (default: system date).
- `--keywords "a OR b"` — disambiguate news for common-word names (Increase, Ramp…).
- `--json` — raw JSON. `--no-gdelt`, `--no-github` — skip those collectors.

## Layout
```
last_quarter.py      CLI + concurrent fan-out + compact printer
lib/http.py          stdlib fetch (UA, timeout, throttle) — never raises
lib/window.py        trailing-90d window + date parsing + this/prior/out bucketing
lib/careers.py       Ashby / Greenhouse / Lever resolver (non-empty guard); composition+freshness
lib/news.py          Google News RSS + GDELT; common-word + event-verb filters
lib/blog.py          feed autodiscovery + RSS/Atom parse
lib/edgar.py         ticker→CIK (title-match only) → CIK-scoped 8-K/10-Q; public only
lib/github.py        org releases; collapses automated SDK bumps to a cadence note
```

## Known limits (by design; synthesis layer or paid keys cover them)
- Greenhouse departments need `?content=true` — currently null for Greenhouse boards.
- Feedless blogs return `empty` → fetch `/blog` HTML directly (Firecrawl for JS shells).
- Common-word company names (e.g. Increase) have irreducibly noisy free news → trust
  careers/blog/GitHub and use Exa (paid) for entity-resolved news.
- Verified live 2026-07-01 against Linear, Datadog, Brightwheel, AirOps, Ramp, Increase.
