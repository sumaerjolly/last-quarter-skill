"""Exa collector (paid, EXA_API_KEY) — entity-resolved, date-filtered company news.

Fixes the free tier's worst weakness: common-word name collisions. Free Google News on
"Reflow" returns 32 "Reflow Medical" / "DOM reflow" hits; Exa's neural search anchored on
the domain resolves the RIGHT company and returns real publisher URLs (not opaque redirects).
Key-gated: activates only when EXA_API_KEY is set. Self-serve key (free trial available).
"""
from __future__ import annotations

import os

from .http import post_json
from .identity import brand_slug, registrable_domain
from .window import bucket

API = "https://api.exa.ai/search"


def available() -> bool:
    return bool(os.getenv("EXA_API_KEY"))


def classify_result(url: str, title: str, text: str, name: str, domain: str) -> str:
    """'collision' (same-name different company's own domain), 'drop' (not about this
    company), or 'keep'. Pure — unit-tested offline."""
    want = registrable_domain(domain)
    our_slug = brand_slug(domain)
    outlet = registrable_domain(url)
    if our_slug and our_slug in brand_slug(url) and outlet != want:
        return "collision"
    n = name.lower()
    if n not in (title or "").lower() and n not in (text or "").lower() and outlet != want:
        return "drop"
    return "keep"


def collect(name: str, domain: str, window: dict, keywords: str | None = None) -> dict:
    key = os.getenv("EXA_API_KEY")
    if not key:
        return {"source": "exa", "status": "skipped", "note": "no EXA_API_KEY set"}

    # Tight, entity-anchored query. A long list of event types makes Exa return the whole
    # semantic CATEGORY (adjacent companies' funding), so keep it about THIS company.
    query = f'News and announcements about "{name}", the company at {domain}.'
    if keywords:
        query += f" {keywords}"
    body = {
        "query": query, "numResults": 15, "type": "auto",
        "startPublishedDate": f"{window['start']}T00:00:00.000Z",
        "endPublishedDate": f"{window['end']}T23:59:59.000Z",
        "contents": {"text": {"maxCharacters": 300}},
    }
    code, data = post_json(API, body, headers={"x-api-key": key})
    if code == 401:
        return {"source": "exa", "status": "error", "error": "Exa 401 — bad EXA_API_KEY",
                "note": "Exa rejected the key."}
    if code == 0 or not isinstance(data, dict):
        return {"source": "exa", "status": "error", "error": f"Exa unreachable (code {code})",
                "note": "Exa fetch failed — not confirmed empty."}
    results = data.get("results") or []

    want = registrable_domain(domain)
    signals, collisions = [], set()
    for r in results:
        url = r.get("url") or ""
        outlet = registrable_domain(url)
        title = (r.get("title") or "").strip()
        text = (r.get("text") or "").strip()
        verdict = classify_result(url, title, text, name, domain)
        if verdict == "collision":
            collisions.add(outlet)
            continue
        if verdict == "drop":
            continue
        date = r.get("publishedDate") or r.get("published_date")
        if date and bucket(date, window) not in ("in_window", "unknown"):
            continue
        signals.append({
            "title": title, "url": url, "date": date,
            "outlet": "self" if outlet == want else outlet,  # flag first-party posts
            "text": text[:280],
        })
    noisy = bool(collisions) and not keywords
    if noisy:
        note = (f"Same-name companies detected ({', '.join(sorted(collisions))}) — remaining "
                f"results may still mix entities. Add --keywords '<what they do>' for precision.")
    elif signals:
        note = "Entity-resolved news via Exa (real URLs, name-collision-safe)."
    else:
        note = "Exa returned no in-window results for this company."
    return {
        "source": "exa", "status": "active" if signals else "empty",
        "count": len(signals), "noisy": noisy, "collisions": sorted(collisions),
        "note": note, "signals": signals[:15],
    }
