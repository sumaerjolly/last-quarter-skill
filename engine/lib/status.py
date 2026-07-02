"""Status-page incident feed → Risk/negative signal. Free (Atlassian Statuspage,
Instatus, BetterStack). No entity risk: status.{domain} is the company's own page."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .http import fetch_text
from .identity import brand_slug, registrable_domain
from .window import bucket


def _candidates(domain: str) -> list[str]:
    reg, slug = registrable_domain(domain), brand_slug(domain)
    return [
        f"https://status.{reg}/history.rss",
        f"https://status.{reg}/history.atom",
        f"https://{slug}.statuspage.io/history.rss",
        f"https://{slug}status.com/history.rss",
    ]


def _parse(text: str, window: dict) -> list[dict]:
    try:
        root = ET.fromstring(text.encode("utf-8", "replace"))
    except ET.ParseError:
        return []
    entries = list(root.iter("item")) + [e for e in root.iter() if e.tag.endswith("}entry")]
    out = []
    for el in entries:
        def gt(*names):
            for n in names:
                for child in el:
                    if child.tag == n or child.tag.endswith("}" + n):
                        return (child.text or "").strip() or child.get("href", "")
            return ""
        title = gt("title")
        date = gt("pubDate", "published", "updated", "date")
        link = gt("link", "guid")
        if title and bucket(date, window) == "in_window":
            out.append({"title": title, "date": date, "url": link})
    return out


def collect(domain: str, window: dict) -> dict:
    saw_response = False
    for url in _candidates(domain):
        code, text = fetch_text(url)
        if code == 0:
            continue  # transport error on this candidate
        saw_response = True
        if code != 200 or "<" not in text:
            continue
        incidents = _parse(text, window)
        return {
            "source": "status", "status": "active" if incidents else "empty",
            "found": url, "count": len(incidents),
            "note": None if incidents else "Status page found, no incidents in the last 90 days.",
            "signals": incidents,
        }
    if not saw_response:
        return {"source": "status", "status": "error",
                "error": "status page fetch failed",
                "note": "Status-page lookups failed (network) — not confirmed absent."}
    return {"source": "status", "status": "empty",
            "note": "No status/incident page found (tried status.{domain}, {brand}.statuspage.io)."}
