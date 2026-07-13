"""JSON-LD schema.org JobPosting fallback — for careers sites with no recognizable ATS.

Truly custom / in-house careers pages usually still embed schema.org `JobPosting` markup for
Google Jobs indexing, with an ABSOLUTE `datePosted`. Lower fidelity than a real ATS (no
department taxonomy) but real dates, and ATS-agnostic. Entity-guarded: a posting that names a
DIFFERENT `hiringOrganization` is dropped so an embedded third-party widget can't inject
someone else's jobs. Structurally a clone of blog.py's HTML-listing fallback.
"""
from __future__ import annotations

import html as _html
import json
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from .http import fetch_text
from .identity import brand_slug, norm_company, registrable_domain
from .window import parse_dt

_LD = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_JOB_HREF = re.compile(
    r'href=["\'](/(?:job|jobs|careers?|position|positions|opening|openings)/'
    r'[a-z0-9][a-z0-9\-/]{3,})["\']', re.I)
_DETAIL_CAP = 20  # max detail pages fetched when postings live on their own pages


def _plain(s) -> str:
    return _TAG.sub(" ", _html.unescape(str(s or "")))


def _iter_jobpostings(blob: str):
    """Yield JobPosting dicts from one JSON-LD blob (handles single obj, list, @graph)."""
    try:
        data = json.loads(blob)
    except Exception:
        return
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if "JobPosting" in types:
                yield node
            elif "@graph" in node:
                g = node["@graph"]
                stack.extend(g if isinstance(g, list) else [g])


def _extract(html: str) -> list[dict]:
    out = []
    for blob in _LD.findall(html or ""):
        out.extend(_iter_jobpostings(blob.strip()))
    return out


def _loc_str(jp: dict) -> str | None:
    loc = jp.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, dict):
        addr = loc.get("address")
        if isinstance(addr, dict):
            parts = [addr.get("addressLocality"), addr.get("addressRegion"),
                     addr.get("addressCountry")]
            return ", ".join(p for p in parts if isinstance(p, str) and p) or None
    return None


def _entity_ok(jp: dict, want_tokens: set) -> bool:
    """Drop postings whose hiringOrganization names a company sharing NO token with the target.
    Absent org (posting on the company's own page) passes."""
    org = jp.get("hiringOrganization")
    if isinstance(org, list):
        org = org[0] if org else None
    if isinstance(org, dict) and org.get("name"):
        got = set(norm_company(org["name"]).split())
        if got and want_tokens and not (got & want_tokens):
            return False
    return True


def _to_job(jp: dict) -> dict | None:
    title = jp.get("title")
    if not title:
        return None
    dt = parse_dt(jp.get("datePosted"))
    return {
        "title": _plain(title) if "<" in str(title) else str(title).strip(),
        "department": None,
        "location": _loc_str(jp),
        "url": jp.get("url") or jp.get("@id"),
        "date": dt.date().isoformat() if dt else None,
        "text": _plain(jp.get("description")),
    }


def collect(domain: str, name: str | None, window: dict, pages: dict) -> dict | None:
    """`pages` = {path: html} already fetched by careers discovery (no refetch here for the
    listing shape). Returns a board dict (careers.py shape) or None."""
    reg = registrable_domain(domain)
    want = {w for w in (set(norm_company(name or "").split()) | {brand_slug(domain)}) if w}

    def _collect_from(htmls) -> list[dict]:
        found = []
        for html in htmls:
            for jp in _extract(html):
                if _entity_ok(jp, want):
                    j = _to_job(jp)
                    if j:
                        found.append(j)
        return found

    # Shape (a): the listing page embeds every posting.
    postings = _collect_from((pages or {}).values())
    via = "listing"

    # Shape (b): postings live on their own detail pages — collect hrefs, fetch, extract.
    if not postings:
        hrefs, seen = [], set()
        for html in (pages or {}).values():
            for path in _JOB_HREF.findall(html or ""):
                u = urllib.parse.urljoin(f"https://{reg}", path)
                if u not in seen:
                    seen.add(u)
                    hrefs.append(u)
        if not hrefs:
            return None
        with ThreadPoolExecutor(max_workers=12) as pool:
            detail_htmls = list(pool.map(
                lambda u: (fetch_text(u, maxbytes=120000) or (0, ""))[1], hrefs[:_DETAIL_CAP]))
        postings = _collect_from(detail_htmls)
        via = "detail"

    if not postings:
        return None

    seen, jobs = set(), []
    for j in postings:
        k = (j["title"] or "").lower()[:80]
        if k and k not in seen:
            seen.add(k)
            jobs.append(j)

    return {
        "ats": "json-ld", "token": reg,
        "board_url": f"https://{reg}/careers",
        "api_url": None,
        "jobs": jobs,
        "note": (f"Parsed from schema.org JobPosting markup on the careers site ({via} shape); "
                 f"department taxonomy unavailable. Entity-checked against '{name}'."),
    }
