"""Workday collector — enterprise/public ATS via the unauthenticated `cxs` JSON API.

Discovered by link on the company's OWN careers page (never guessed), so identity is
link-verified before we ever call this. Fills the big gap left by the Ashby/Greenhouse/Lever
trio, which is a startup-shaped net that Remitly-class companies swim right through.

Date honesty: the list payload only carries a RELATIVE `postedOn` ("Posted 3 Days Ago",
"Posted 30+ Days Ago"). We convert what we can against the window end; "30+ days" is a floor,
not a date, so those roles get no date and fall out of the in-window count (a lower bound, by
design). For the newest N roles we deep-fetch the detail page, which carries an ABSOLUTE
`startDate` and the full JD text (feedstock for jd_mining). Verified 2026-07-13 vs remitly.wd5.
"""
from __future__ import annotations

import html as _html
import http.cookiejar
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .http import UA, fetch_json, post_json
from .window import parse_dt

_TAG = re.compile(r"<[^>]+>")
_DEEP_CAP = 15   # max detail pages fetched for JD text + precise dates
_LIST_CAP = 100  # max postings pulled from the list endpoint

_REL_TODAY = re.compile(r"posted\s+today", re.I)
_REL_YEST = re.compile(r"posted\s+yesterday", re.I)
_REL_NDAYS = re.compile(r"posted\s+(\d+)\s*(\+)?\s*days?\s+ago", re.I)


def _plain(s: str | None) -> str:
    return _TAG.sub(" ", _html.unescape(s or ""))


def _posted_date(posted_on: str | None, today: date) -> str | None:
    """Relative Workday `postedOn` text -> ISO date string vs `today`. '30+ Days Ago' is a
    FLOOR (unknown exact date) -> None; never fabricate. Unparseable -> None."""
    if not posted_on or today is None:
        return None
    s = posted_on.strip()
    if _REL_TODAY.search(s):
        return today.isoformat()
    if _REL_YEST.search(s):
        return (today - timedelta(days=1)).isoformat()
    m = _REL_NDAYS.search(s)
    if m:
        if m.group(2):  # the "+" in "30+ Days Ago" -> at least N days, exact unknown
            return None
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    return None


def _site_candidates(tenant: str, hint: str | None) -> list[str]:
    """Site slug is often absent from the careers-page link. Try the hint first, then the
    common Workday naming conventions derived from the tenant."""
    tt = tenant[:1].upper() + tenant[1:]
    cands = [hint, f"{tt}_Careers", f"{tt}Careers", "Careers", "careers",
             "External", f"{tt}_External", tt, tenant]
    seen, out = set(), []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _fetch_page(jobs_url: str, offset: int) -> dict | None:
    code, data = post_json(jobs_url, {"appliedFacets": {}, "limit": 20,
                                      "offset": offset, "searchText": ""}, timeout=10)
    return data if code == 200 and isinstance(data, dict) else None


def _fetch_page_cookied(board_page: str, jobs_url: str, offset: int) -> dict | None:
    """Some tenants gate the POST behind a session cookie set by GETting the board page."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        opener.open(urllib.request.Request(board_page, headers={"User-Agent": UA}),
                    timeout=10).read(1)
        body = json.dumps({"appliedFacets": {}, "limit": 20,
                           "offset": offset, "searchText": ""}).encode("utf-8")
        req = urllib.request.Request(
            jobs_url, data=body, method="POST",
            headers={"User-Agent": UA, "Content-Type": "application/json",
                     "Accept": "application/json"})
        with opener.open(req, timeout=10) as resp:
            return json.loads(resp.read() or b"null")
    except Exception:
        return None


def collect(tenant: str, wd: str, site_hint: str | None, window: dict) -> dict | None:
    """Resolve the site slug, pull postings, deep-fetch the newest N for JD text + precise
    dates. Returns a board dict in the SAME shape the careers.py parsers return, or None."""
    base = f"https://{tenant}.wd{wd}.myworkdayjobs.com"
    today_dt = parse_dt(window["end"])
    today = today_dt.date() if today_dt else None

    site, first = None, None
    for cand in _site_candidates(tenant, site_hint):
        jobs_url = f"{base}/wday/cxs/{tenant}/{cand}/jobs"
        data = _fetch_page(jobs_url, 0)
        if data is None:  # cookie-gated tenant? try once through a cookie jar
            data = _fetch_page_cookied(f"{base}/en-US/{cand}", jobs_url, 0)
        if isinstance(data, dict) and data.get("jobPostings"):
            site, first = cand, data
            break
    if not site or not first:
        return None

    cxs = f"{base}/wday/cxs/{tenant}/{site}"
    jobs_url = f"{cxs}/jobs"
    total = int(first.get("total") or 0)
    postings = list(first.get("jobPostings") or [])

    # Department rollup from the jobFamilyGroup facet (aggregate over ALL open roles — the
    # list payload has no per-job department). careers.collect uses this when it has no
    # per-job dept, and labels it all-listed.
    dept_facets = []
    for facet in first.get("facets") or []:
        if facet.get("facetParameter") == "jobFamilyGroup":
            dept_facets = [(v.get("descriptor"), v.get("count"))
                           for v in (facet.get("values") or []) if v.get("descriptor")]
            break

    offsets = list(range(20, min(total, _LIST_CAP), 20))
    if offsets:
        with ThreadPoolExecutor(max_workers=max(1, len(offsets))) as pool:
            for data in pool.map(lambda o: _fetch_page(jobs_url, o), offsets):
                if isinstance(data, dict):
                    postings.extend(data.get("jobPostings") or [])

    jobs = []
    for p in postings:
        ext = p.get("externalPath") or ""
        jobs.append({
            "title": p.get("title"),
            "department": None,  # not in the list payload; facets are aggregate-only
            "location": p.get("locationsText"),
            "url": f"{base}/en-US/{site}{ext}" if ext else base,
            "date": _posted_date(p.get("postedOn"), today),
            "text": None,
            "_ext": ext,
        })

    # Deep-fetch the newest N: upgrades the relative date to the absolute startDate and pulls
    # JD text for jd_mining. Prefer roles that already parsed a date (the recent ones).
    deep = sorted([j for j in jobs if j["date"]], key=lambda x: x["date"], reverse=True)
    deep = (deep or jobs)[:_DEEP_CAP]

    def _detail(j: dict) -> None:
        if not j.get("_ext"):
            return
        code, d = fetch_json(f"{cxs}{j['_ext']}")
        jpi = (d or {}).get("jobPostingInfo") if isinstance(d, dict) else None
        if not isinstance(jpi, dict):
            return
        j["text"] = _plain(jpi.get("jobDescription"))
        sd = jpi.get("startDate")
        if sd and parse_dt(sd):
            j["date"] = parse_dt(sd).date().isoformat()  # absolute beats the estimate
        if jpi.get("externalUrl"):
            j["url"] = jpi["externalUrl"]

    if deep:
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(_detail, deep))

    for j in jobs:
        j.pop("_ext", None)

    note = ("Workday truncates posting ages past 30 days — posted-in-window is a LOWER "
            "BOUND; roles shown as '30+ days ago' are excluded (date unknown), not "
            "confirmed old.")
    if total > len(jobs):
        note = f"Sampled {len(jobs)} of {total} open roles. " + note
    return {
        "ats": "workday", "token": f"{tenant}:wd{wd}:{site}",
        "board_url": f"{base}/en-US/{site}",
        "api_url": jobs_url,
        "jobs": jobs,
        "dept_facets": dept_facets,
        "note": note,
    }
