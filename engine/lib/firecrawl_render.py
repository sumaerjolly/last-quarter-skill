"""Firecrawl collector (paid, FIRECRAWL_API_KEY) — render JS-shell blog listings the free
tier can't read. COST-DISCIPLINED:
  - escalation-only: called only when the free blog collector returns a true JS shell.
  - listing only, NEVER per-post: max 2 scrapes/company (/blog then /resources). We do not
    fan out to N post pages (the credit bomb).
  - the rendered listing gives titles + URLs but usually no dates → we recover customer-wins
    + competitive + "what they publish" (date-agnostic), NOT dated launch recency.
"""
from __future__ import annotations

import os
import re

from .http import post_json
from .identity import registrable_domain

API = "https://api.firecrawl.dev/v1/scrape"
_POST = re.compile(
    r"/(?:blog|resources|news|posts|insights|customers|case-stud\w+|stories)/[a-z0-9][a-z0-9-]{4,}",
    re.I)
_MD_LINK = re.compile(r"\[([^\]\n]{6,100})\]\((https?://[^)\s]+)\)")


def available() -> bool:
    return bool(os.getenv("FIRECRAWL_API_KEY"))


def _scrape(url: str):
    key = os.getenv("FIRECRAWL_API_KEY")
    code, data = post_json(
        API, {"url": url, "formats": ["markdown", "links"], "onlyMainContent": True},
        headers={"Authorization": f"Bearer {key}"}, timeout=60)
    if code != 200 or not isinstance(data, dict) or not data.get("success"):
        return None
    d = data.get("data") or {}
    return (d.get("markdown") or ""), (d.get("links") or [])


def render_blog(domain: str) -> dict | None:
    """One rendered listing → undated {title,url} posts. Returns None if nothing usable.
    Costs 1–2 Firecrawl credits (stops on the first path that yields posts)."""
    reg = registrable_domain(domain)
    credits = 0
    for path in ("/blog", "/resources"):  # 2 attempts MAX — never per-post
        res = _scrape(f"https://{reg}{path}")
        credits += 1
        if not res:
            continue
        md, links = res
        posts, seen = [], set()
        # prefer markdown [Title](url) pairs (gives real titles), then bare links
        for m in _MD_LINK.finditer(md):
            title, url = m.group(1).strip(), m.group(2)
            if _POST.search(url) and url not in seen:
                seen.add(url)
                posts.append({"title": title, "url": url, "date": None})
        for url in links:
            if _POST.search(url) and url not in seen:
                seen.add(url)
                slug = url.rstrip("/").split("/")[-1].replace("-", " ").title()
                posts.append({"title": slug, "url": url, "date": None})
        if len(posts) >= 3:
            return {"path": path, "posts": posts[:25], "credits": credits}
    return None
