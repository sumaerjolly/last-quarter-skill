"""Blog / changelog collector — feed autodiscovery + RSS/Atom parse."""
from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET

from .http import fetch_text
from .window import bucket

_ALT = re.compile(
    r'<link[^>]+rel=["\']alternate["\'][^>]*>', re.I)
_HREF = re.compile(r'href=["\']([^"\']+)["\']', re.I)
_TYPE = re.compile(r'type=["\']application/(rss|atom)\+xml["\']', re.I)

COMMON_PATHS = [
    "/blog/rss.xml", "/blog/index.xml", "/rss/changelog.xml", "/changelog/rss.xml",
    "/rss.xml", "/feed", "/feed.xml", "/atom.xml", "/blog/feed", "/changelog.xml",
]


def _base(domain: str) -> str:
    d = domain.replace("https://", "").replace("http://", "").split("/")[0]
    return f"https://{d}"


def discover_feeds(base: str) -> list[str]:
    feeds = []
    for page in ("/blog", "/changelog", "/news", "/"):
        code, html = fetch_text(base + page)
        if code != 200:
            continue
        for tag in _ALT.findall(html):
            if _TYPE.search(tag):
                m = _HREF.search(tag)
                if m:
                    feeds.append(urllib.parse.urljoin(base + page, m.group(1)))
    return list(dict.fromkeys(feeds))


def _parse_feed(url: str, window: dict) -> list[dict]:
    code, text = fetch_text(url)
    if code != 200 or "<" not in text:
        return []
    try:
        root = ET.fromstring(text.encode("utf-8", "replace"))
    except ET.ParseError:
        return []
    items = []
    # RSS <item> then Atom <entry>
    for el in list(root.iter("item")) + [e for e in root.iter()
                                         if e.tag.endswith("}entry")]:
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
            items.append({"title": title, "date": date, "url": link, "feed": url})
    return items


def collect(domain: str, window: dict) -> dict:
    base = _base(domain)
    feeds = discover_feeds(base)
    tried = list(feeds)
    items: list[dict] = []
    for f in feeds:
        items += _parse_feed(f, window)
    if not items:  # fall back to common paths
        for path in COMMON_PATHS:
            url = base + path
            tried.append(url)
            found = _parse_feed(url, window)
            if found:
                items += found
                break
    seen, uniq = set(), []
    for it in sorted(items, key=lambda x: str(x["date"]), reverse=True):
        k = it["title"].lower()[:80]
        if k not in seen:
            seen.add(k)
            uniq.append(it)
    return {
        "source": "blog", "status": "active" if uniq else "empty",
        "count": len(uniq), "feeds_used": [i["feed"] for i in uniq[:1]] or feeds,
        "note": None if uniq else "No feed found or no in-window posts. If the /blog page "
                "renders posts in HTML, fetch it directly; use Firecrawl only for JS shells.",
        "signals": uniq[:20],
    }
