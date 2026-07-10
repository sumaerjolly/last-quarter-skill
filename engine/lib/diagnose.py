"""`--diagnose` — one-command health check across all live integrations. OSS support becomes
"run --diagnose and paste the output". ok=True→OK, False→FAIL, None→skipped/no-key.
Costs at most: 1 Exa call + 1 PDL credit (only if those keys are set)."""
from __future__ import annotations

import os

from .http import fetch_full, fetch_json, fetch_text, post_json


def _probe(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, str(e)[:60]
    return name, ok, detail


def _ashby():
    c, d = fetch_json("https://api.ashbyhq.com/posting-api/job-board/airops")
    n = len((d or {}).get("jobs") or []) if isinstance(d, dict) else 0
    return (c == 200 and n > 0), f"{n} jobs"


def _greenhouse():
    c, d = fetch_json("https://boards-api.greenhouse.io/v1/boards/datadog/jobs")
    n = len((d or {}).get("jobs") or []) if isinstance(d, dict) else 0
    return (c == 200 and n > 0), f"{n} jobs"


def _lever():
    c, d = fetch_json("https://api.lever.co/v0/postings/brightwheel?mode=json")
    return (c == 200), f"HTTP {c} (reachable)"


def _google_news():
    c, t = fetch_text('https://news.google.com/rss/search?q=%22Datadog%22%20when:30d&hl=en-US')
    return (c == 200 and "<item>" in t), f"HTTP {c}, items={'<item>' in t}"


def _hackernews():
    c, d = fetch_json("https://hn.algolia.com/api/v1/search_by_date?query=Datadog&tags=story")
    return (c == 200 and isinstance(d, dict)), f"HTTP {c}"


def _statuspage():
    c, t = fetch_text("https://www.githubstatus.com/history.rss")
    return (c == 200 and "<rss" in t.lower()), f"HTTP {c}"


def _sec():
    from .edgar import _sec_headers
    c, d = fetch_json("https://www.sec.gov/files/company_tickers.json", headers=_sec_headers())
    ok = c == 200 and isinstance(d, dict) and len(d) > 100
    return ok, f"HTTP {c}, {len(d) if isinstance(d, dict) else 0} tickers"


def _github():
    c, d = fetch_json("https://api.github.com/orgs/datadog",
                      headers={"Accept": "application/vnd.github+json"})
    return (c == 200), f"HTTP {c}"


def _webstack():
    from .webstack import detect
    c, body, hdrs = fetch_full("https://www.vanta.com", maxbytes=300_000)
    n = len(detect(body.decode("utf-8", "replace"), hdrs)) if c == 200 else 0
    return (c == 200 and n > 0), f"{n} fingerprints on vanta.com"


def _exa():
    if not os.getenv("EXA_API_KEY"):
        return None, "no key"
    c, d = post_json("https://api.exa.ai/search", {"query": "Datadog", "numResults": 1},
                     headers={"x-api-key": os.environ["EXA_API_KEY"]})
    return (c == 200), f"HTTP {c} (1 call spent)"


def _firecrawl():
    return (None if not os.getenv("FIRECRAWL_API_KEY") else True,
            "no key" if not os.getenv("FIRECRAWL_API_KEY") else "key set (not probed — costs a credit)")


def _pdl():
    if not os.getenv("PDL_API_KEY"):
        return None, "no key"
    c, d = post_json("https://api.peopledatalabs.com/v5/person/search",
                     {"query": {"term": {"job_company_website": "datadoghq.com"}}, "size": 1},
                     headers={"X-Api-Key": os.environ["PDL_API_KEY"]})
    return (c == 200), f"HTTP {c} (<=1 credit spent)"


_CHECKS = [
    ("ashby", _ashby), ("greenhouse", _greenhouse), ("lever", _lever),
    ("google_news", _google_news), ("gdelt", lambda: (None, "skipped (throttled API)")),
    ("hackernews", _hackernews), ("statuspage", _statuspage), ("sec_edgar", _sec),
    ("github", _github), ("webstack", _webstack),
    ("exa", _exa), ("firecrawl", _firecrawl), ("pdl", _pdl),
]


def render() -> str:
    lines = ["last-quarter --diagnose  ·  integration health", ""]
    for name, fn in _CHECKS:
        n, ok, detail = _probe(name, fn)
        sym = "OK  " if ok is True else ("—   " if ok is None else "FAIL")
        lines.append(f"  [{sym}] {name:13} {detail}")
    return "\n".join(lines)
