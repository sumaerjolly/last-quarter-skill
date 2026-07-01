# Source Cookbook — verified endpoints

All endpoints below were probed live on 2026-07-01 against Linear, Datadog, Brightwheel,
and AirOps. Fields listed are the ones that actually appear in responses. Fetch with
`curl`/`Bash` or `WebFetch`.

---

## Careers / ATS (free, structured JSON)

Resolve `{token}` from the domain brand (`airops.com` → `airops`, `mybrightwheel.com` →
`brightwheel`). Try the three below; **accept the first with a non-empty jobs array.**

### Ashby  (Linear, AirOps, Brightwheel use this)
```
https://api.ashbyhq.com/posting-api/job-board/{token}
```
- `.jobs[]` fields: `title`, `department`, `team`, `location`, `employmentType`,
  `isRemote`, `workplaceType`, `publishedAt` (ISO), `updatedAt`, `jobUrl`,
  `descriptionPlain`.
- **Trajectory field:** `publishedAt`. Bucket by it for in-window vs prior.
- `isListed: true` = live posting.

### Greenhouse  (Datadog uses this)
```
https://boards-api.greenhouse.io/v1/boards/{token}/jobs
```
- `.jobs[]` fields: `title`, `location.name`, `absolute_url`, `first_published` (ISO),
  `updated_at`, `metadata`.
- **Trajectory field:** `first_published`.
- Departments: add `?content=true`, or call `.../boards/{token}/departments`.

### Lever
```
https://api.lever.co/v0/postings/{token}?mode=json
```
- Array of postings: `text` (title), `categories.team/department/location`,
  `createdAt` (epoch ms), `hostedUrl`.
- **GOTCHA (verified):** returns `200` with `[]` for a wrong/dead token
  (Brightwheel's Lever returned 2 bytes). Require length > 0 before trusting.

**No ATS hit:** company likely on Workday/custom. Fall back to Google News + `WebFetch`
of `/careers` (Firecrawl if it's an empty JS shell). Don't invent a job count.

**Survivorship bias — do not report careers as a clean this-90-vs-prior-90 delta.** All
three APIs return only *currently open* roles; filled/closed roles disappear, so the
prior-90 bucket is always under-counted. Report **composition + freshness** instead:
"X of N open roles posted in-window, concentrated in {departments}", plus standout
senior reqs. Use persistent-history sources (news, blog, GitHub, EDGAR) for clean trends.

---

## News (free)

### Google News RSS  (primary — best for company-specific)
```
https://news.google.com/rss/search?q=%22{Company}%22%20when:90d&hl=en-US&gl=US&ceid=US:en
```
- `when:90d` scopes to the window. Parse `<item>`: `title`, `link`, `pubDate`, `source`.
- Verified: AirOps query surfaced the Quill launch + AI-search positioning items.
- **Entity-check** each hit for same-name collisions before including.

### GDELT  (backup only — rate-limited)
```
https://api.gdeltproject.org/api/v2/doc/doc?query=%22{Company}%22&mode=artlist&format=json&timespan=3months
```
- **Throttle to 1 request / 5 seconds** or it returns a plaintext rate-limit notice
  instead of JSON. `.articles[]`: `seendate`, `domain`, `title`, `url`.

---

## Public company — SEC EDGAR (free; only if routed public)

### 1. Name/ticker → CIK
```
https://www.sec.gov/files/company_tickers.json
```
Match on `ticker` or `title`. **Miss = private → skip EDGAR.** (Verified: `DDOG → CIK
1561550`.)

### 2. Filings full-text search (in-window)
```
https://efts.sec.gov/LATEST/search-index?q=%22{Company}%22&forms=8-K&startdt={from}&enddt={to}
```
- **Requires header:** `User-Agent: {your name} {email}` (SEC blocks unidentified bots).
- `.hits.hits[]`: `_id` (accession:file), `_source.ciks`, `_source.file_date`.
- Verified: 9 Datadog 8-Ks in Apr–Jun 2026.
- **8-K** = material events (exec changes, M&A, results, departures). **10-Q** =
  quarterly results + risk factors (stated priorities). Change `forms=` accordingly.

---

## Blog / changelog (free for most)

1. **Feed autodiscovery:** `WebFetch` `/blog` and `/changelog`; read
   `<link rel="alternate" type="application/rss+xml">` (or `atom+xml`) → real feed URL.
2. **Common-path fallback** (paths differ per site — verified examples):
   - Linear changelog: `https://linear.app/rss/changelog.xml` (242 items)
   - Brightwheel blog: `https://mybrightwheel.com/blog/rss.xml` (10 items)
   - Datadog blog: `https://www.datadoghq.com/blog/index.xml`
   - Other guesses: `/rss.xml`, `/blog/rss.xml`, `/feed`, `/blog/index.xml`.
3. **No feed** (verified: AirOps, a Webflow SPA): plain `WebFetch` the `/blog` index —
   post titles + `/blog/{slug}` links are in the server-rendered HTML (AirOps returned
   194 post links). Firecrawl only if the fetch is an empty JS shell.

Parse dated `<item>`/`<entry>`; keep in-window items. Post dates give launch cadence.

---

## GitHub releases (free; dev-tool companies only)
```
https://api.github.com/orgs/{org}/repos?sort=updated&per_page=20
https://api.github.com/repos/{org}/{repo}/releases
```
- `releases[]`: `name`, `tag_name`, `published_at`, `body`. Bucket by `published_at`.
- Unauthenticated rate limit is low (~60/hr); a `GITHUB_TOKEN` raises it.

---

## Paid upgrades ("add keys → awesome")

| Tool | Env | Unlocks |
|---|---|---|
| **Firecrawl** | `FIRECRAWL_API_KEY` | JS-rendered changelog/careers/blog a plain fetch can't read |
| **Exa** | `EXA_API_KEY` | Neural, date-filtered "what happened at X" news (`startPublishedDate`) |
| **Apify** | `APIFY_API_TOKEN` | LinkedIn company posts + headcount trend actors |
| **PredictLeads** | `PREDICTLEADS_*` | Purpose-built: job openings + news events + technographics per domain |
| **Crustdata / TheirStack** | keys | Headcount + tech-stack trend over time |

All are optional. Report which are active as "sources active: N of M".
