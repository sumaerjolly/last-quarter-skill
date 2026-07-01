"""News collector — Google News RSS (primary) + GDELT (throttled backup)."""
from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET

from .http import fetch_json, fetch_text
from .window import bucket

# Names that are also ordinary English words → news RSS is unreliable without keywords.
COMMON_WORD_NAMES = {
    "increase", "ramp", "notion", "linear", "stripe", "square", "block", "gong",
    "chime", "brex", "front", "loom", "figma", "vercel", "retool", "amplitude",
    "monday", "wave", "path", "rippling", "pilot", "column", "mercury", "unit",
}


# Event verbs that make a headline an actual ABM signal (funding, launch, exec, M&A...).
_EVENT = re.compile(
    r"\b(raise[sd]?|raising|funding|seed|series\s+[a-e]|valuation|valued|launch\w*|"
    r"unveil\w*|introduc\w*|debut\w*|appoint\w*|name[sd]?\s+(?:new|its|a)|hire[sd]?|"
    r"promot\w*|acqui\w+|merg\w+|partner\w*|expand\w*|open\w*\s+office|layoff\w*|"
    r"laid\s+off|cuts?\s+jobs|sue[sd]?|lawsuit|breach|outage|hack\w*|ipo|"
    r"round|invest\w*|customer\w*|milestone)\b", re.I)


def _common_word_usage(name: str) -> re.Pattern:
    """Matches titles that use the brand token as an ordinary word (verb/noun), e.g.
    'increase in', '$70M increase', 'increase chance' — used to drop false positives."""
    n = re.escape(name)
    after = r"(in|of|for|by|to|the|a|an|from|on|over|during|among|chance|risk|rate|rates|" \
            r"your|his|her|their|its|due|significantly|slightly|dramatically)"
    return re.compile(rf"(?:[%$]\s*\d|\d[\d.,]*\s*(?:million|billion|percent|%)?\s+{n}\b)"
                      rf"|\b{n}\s+{after}\b", re.I)


def _google_news(name: str, window: dict, keywords: str | None) -> list[dict]:
    query = f'"{name}"'
    if keywords:
        query += f" {keywords}"
    query += f' when:{window["days"]}d'
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    code, text = fetch_text(url)
    if code != 200 or "<item>" not in text:
        return []
    out = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        src_el = item.find("{http://www.w3.org/2005/Atom}source") or item.find("source")
        source = (src_el.text if src_el is not None else "") or ""
        if bucket(pub, window) in ("in_window", "unknown"):
            out.append({"title": title, "url": link, "date": pub,
                        "outlet": source, "via": "google_news"})
    return out


def _gdelt(name: str, window: dict) -> list[dict]:
    q = urllib.parse.quote(f'"{name}"')
    url = (f"https://api.gdeltproject.org/api/v2/doc/doc?query={q}"
           f"&mode=artlist&format=json&timespan={window['days']}days&maxrecords=20")
    # GDELT rate-limits hard; throttle to 1 req / 5s and accept non-JSON as empty.
    code, data = fetch_json(url, throttle_key="gdelt", min_gap=5.0, timeout=15)
    arts = (data or {}).get("articles") if isinstance(data, dict) else None
    if not arts:
        return []
    return [{"title": a.get("title"), "url": a.get("url"),
             "date": a.get("seendate"), "outlet": a.get("domain"), "via": "gdelt"}
            for a in arts]


def collect(name: str, window: dict, use_gdelt: bool = True,
            keywords: str | None = None) -> dict:
    common = name.lower() in COMMON_WORD_NAMES
    items = _google_news(name, window, keywords)

    dropped = 0
    if common and not keywords:  # ordinary-word name → precision over recall
        bad = _common_word_usage(name)
        kept = [it for it in items
                if not bad.search(it.get("title", ""))
                and _EVENT.search(it.get("title", ""))]  # keep only event-bearing news
        dropped = len(items) - len(kept)
        items = kept

    if use_gdelt and len(items) < 3:  # only bother with GDELT when Google News is thin
        items += _gdelt(name, window)
    # de-dupe by title
    seen, uniq = set(), []
    for it in items:
        key = (it.get("title") or "").lower()[:80]
        if key and key not in seen:
            seen.add(key)
            uniq.append(it)

    noisy = common and not keywords
    note = None
    if not uniq and common:
        note = (f"'{name}' is a common word — free news RSS can't disambiguate it "
                f"({dropped} non-event/ordinary-usage headlines dropped). Trust "
                f"blog/careers/GitHub here; use a paid entity-resolved source (Exa) for news.")
    elif not uniq:
        note = ("No in-window news via RSS/GDELT — thin news is normal for private/vertical "
                "SaaS. Verify funding/leadership/negatives via a targeted web search.")
    elif noisy:
        note = (f"'{name}' is a common word — filtered to event-bearing headlines only "
                f"({dropped} dropped); some may still be false positives. Entity-check each, "
                f"and prefer Exa for reliable news on this company.")
    return {
        "source": "news", "status": "active" if uniq else "empty",
        "count": len(uniq), "noisy": noisy, "note": note, "signals": uniq[:20],
    }
