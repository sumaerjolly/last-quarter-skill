"""Blog / changelog collector — feed autodiscovery + RSS/Atom parse."""
from __future__ import annotations

import html as _html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from . import customer_wins
from .http import fetch_text
from .window import bucket, parse_dt

_POST_LINK = re.compile(r'href=["\'](/(?:blog|changelog|news|updates|posts)/[a-z0-9][a-z0-9\-]{4,})["\']', re.I)
_DATE_META = re.compile(
    r'"datePublished"\s*:\s*"([^"]+)"'
    r'|<meta[^>]+article:published_time[^>]+content=["\']([^"\']+)["\']'
    r'|<time[^>]+datetime=["\']([^"\']+)["\']', re.I)
_META_TAG = re.compile(r'<meta[^>]+>', re.I)
_CONTENT = re.compile(r'content=["\']([^"\']+)["\']', re.I)
_HTML_FALLBACK_CAP = 20  # max post pages to fetch when no feed exists

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


def _parse_feed(url: str, window: dict) -> tuple[bool, list[dict]]:
    """Returns (is_feed, in_window_items). is_feed=True means the URL is a real RSS/Atom
    feed (so 0 items = 'quiet quarter', not 'no feed / JS shell')."""
    code, text = fetch_text(url)
    if code != 200 or "<" not in text:
        return False, []
    try:
        root = ET.fromstring(text.encode("utf-8", "replace"))
    except ET.ParseError:
        return False, []
    entries = list(root.iter("item")) + [e for e in root.iter()
                                         if e.tag.endswith("}entry")]
    if not entries:
        return False, []
    items = []
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
            items.append({"title": title, "date": date, "url": link, "feed": url})
    return True, items


def _og_title(html: str) -> str | None:
    """Extract og:title regardless of attribute order (content before or after property)."""
    for tag in _META_TAG.findall(html):
        if "og:title" in tag.lower():
            m = _CONTENT.search(tag)
            if m:
                return _html.unescape(m.group(1))
    return None


def _post_meta(url: str) -> dict | None:
    """Fetch a post page's <head> (byte-capped) and pull (title, date) from JSON-LD/og/<time>."""
    code, html = fetch_text(url, timeout=8, maxbytes=80000)  # meta lives in <head>, near top
    if code != 200:
        return None
    m = _DATE_META.search(html)
    date = next((g for g in m.groups() if g), None) if m else None
    if not date:
        return None
    title = _og_title(html) or url.rstrip("/").split("/")[-1].replace("-", " ").title()
    return {"title": title, "date": date, "url": url}


def _html_listing(base: str, window: dict) -> list[dict]:
    """Free fallback for feedless sites (e.g. Webflow SPAs): scrape the /blog listing for
    post links, then fetch each post's page for its published date. No Firecrawl needed
    when content is server-rendered; reserve Firecrawl for true empty JS shells."""
    slugs: list[str] = []
    seen = set()
    for page in ("/blog", "/changelog", "/updates", "/news"):
        code, html = fetch_text(base + page)
        if code != 200:
            continue
        for path in _POST_LINK.findall(html):
            u = urllib.parse.urljoin(base, path)
            if u not in seen:
                seen.add(u)
                slugs.append(u)
    if not slugs:
        return []
    with ThreadPoolExecutor(max_workers=12) as pool:
        metas = list(pool.map(_post_meta, slugs[:_HTML_FALLBACK_CAP]))
    return [m for m in metas if m and bucket(m["date"], window) == "in_window"]


def collect(domain: str, window: dict, brand: str | None = None) -> dict:
    base = _base(domain)
    feeds = discover_feeds(base)
    tried = list(feeds)
    feed_found = False
    items: list[dict] = []
    for f in feeds:
        ok, found = _parse_feed(f, window)
        feed_found = feed_found or ok
        items += found
    via = "feed"
    if not items:  # try common feed paths
        for path in COMMON_PATHS:
            url = base + path
            tried.append(url)
            ok, found = _parse_feed(url, window)
            feed_found = feed_found or ok
            if found:
                items += found
                break
    if not items:  # last resort: scrape the HTML listing (feedless sites)
        items = _html_listing(base, window)
        if items:
            via = "html-listing"
    seen, uniq = set(), []
    for it in sorted(items, key=lambda x: str(parse_dt(x["date"]) or ""), reverse=True):
        k = it["title"].lower()[:80]
        if k not in seen:
            seen.add(k)
            uniq.append(it)

    # Migration-smell: if many posts share one exact date, the CMS likely reset
    # datePublished on a migration → dates are unreliable (seen on AirOps: 20 @ 2026-06-28).
    date_warn = None
    if uniq:
        dc = Counter(str(parse_dt(x["date"]) or "")[:10] for x in uniq)
        top_date, top_n = dc.most_common(1)[0]
        if top_n >= 5 and top_n >= 0.6 * len(uniq):
            date_warn = (f"{top_n}/{len(uniq)} posts share the date {top_date} — likely a CMS "
                         f"migration reset; treat blog post dates as low-confidence.")

    if uniq:
        note = date_warn
    elif feed_found:
        note = "Blog feed found but no posts in the last 90 days (quiet quarter)."
    else:
        note = ("No feed and no server-rendered posts found — likely a client-side JS "
                "shell. Add a Firecrawl key to render it.")
    return {
        "source": "blog", "status": "active" if uniq else "empty",
        "count": len(uniq), "via": via if uniq else None,
        "feed_found": feed_found,
        "feeds_used": [i["feed"] for i in uniq if i.get("feed")][:1] or feeds,
        "note": note,
        "customer_wins": customer_wins.extract_customer_wins(uniq, brand=brand),
        "signals": uniq[:20],
    }
