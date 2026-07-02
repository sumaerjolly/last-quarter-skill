"""Hacker News (Algolia API) → launches / discussion signal. Free, no key."""
from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone

from .http import fetch_json
from .identity import registrable_domain
from .window import bucket


def collect(name: str, domain: str, window: dict) -> dict:
    start_epoch = int(datetime.fromisoformat(window["start"])
                      .replace(tzinfo=timezone.utc).timestamp())
    q = urllib.parse.quote(f'"{name}"')
    url = (f"https://hn.algolia.com/api/v1/search_by_date?query={q}&tags=story"
           f"&numericFilters=created_at_i>{start_epoch}&hitsPerPage=30")
    code, data = fetch_json(url)
    if code == 0:
        return {"source": "hackernews", "status": "error",
                "error": "HN API unreachable", "note": "HN fetch failed — not confirmed empty."}
    hits = (data or {}).get("hits") if isinstance(data, dict) else None
    if not hits:
        return {"source": "hackernews", "status": "empty", "signals": []}

    want = registrable_domain(domain)
    nl = name.lower()
    items = []
    for h in hits:
        title = h.get("title") or ""
        story_url = h.get("url") or ""
        # entity-check: the name must appear in the title, or the story links to their domain
        if nl not in title.lower() and registrable_domain(story_url) != want:
            continue
        if bucket(h.get("created_at"), window) != "in_window":
            continue
        items.append({
            "title": title,
            "url": story_url or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            "date": h.get("created_at"),
            "points": h.get("points"), "comments": h.get("num_comments"),
            "discussion": f"https://news.ycombinator.com/item?id={h.get('objectID')}",
        })
    items.sort(key=lambda x: x.get("points") or 0, reverse=True)
    return {
        "source": "hackernews", "status": "active" if items else "empty",
        "count": len(items), "signals": items[:15],
    }
