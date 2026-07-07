"""Competitive-dynamics extraction from titles we already collect (blog/news/HN).

"What happened at company X last quarter" IS the competitive-intel question — point the
same signals at a competitor's domain and they read as competitor tracking. This finds the
quarter's explicit competitive EVENTS:
  - displacement_win : brand won a rival's customers ("Why teams switch from X to {brand}")
  - competitor_attack: someone launched/aimed a rival at brand ("X launches {brand} competitor")
  - comparison       : brand bracketed against a rival ("{brand} vs X")

Precision-first (same discipline as customer_wins): the OTHER company must be a proper
noun, not the brand, not a stopword. Built by string concat (not f-strings) so literal
regex braces stay literal.
"""
from __future__ import annotations

import re

from .identity import norm_company

_CO = r"([A-Z][A-Za-z0-9&.'\- ]{1,25}?)"
_STOP = {"we", "i", "you", "your", "our", "the", "this", "that", "it", "ai", "llm", "llms",
         "a", "an", "how", "why", "best", "top", "new", "other", "some", "all", "your",
         "everyone", "everything", "teams", "companies", "customers", "users", "startups"}


def _compiled(brand: str):
    b = re.escape(brand.strip())
    pats = [
        ("displacement_win",
         r"(?:switch\w*\s+(?:from\s+)?|from\s+|leaving\s+|migrat\w+\s+from\s+|ditch\w+\s+)"
         + _CO + r"\s+(?:to|for)\s+" + b + r"\b"),
        ("competitor_attack",
         r"^" + _CO + r"\s+(?:launch\w+|unveil\w+|debut\w+|releas\w+|introduc\w+|ship\w+|"
         r"build\w+|roll\w+\s+out)\s+[^,]*?" + b + r"[^,]{0,20}?"
         r"(?:competitor|rival|alternative|killer|clone)"),
        ("competitor_attack",
         _CO + r"\s+(?:takes?\s+on|challeng\w+|targets?\s+|goes?\s+after|"
         r"wants?\s+to\s+(?:beat|kill)|beats?|rivals?)\s+" + b + r"\b"),
        # brand-then-competitor: competitor is terminal, so bound the lazy capture to the
        # name's end (punctuation / a following lowercase word) or it grabs just "Pr".
        ("comparison", b + r"\s+(?:vs\.?|versus)\s+" + _CO + r"(?=$|[:,\-–|]|\s+[a-z])"),
        ("comparison", _CO + r"\s+(?:vs\.?|versus)\s+" + b),
    ]
    return [(kind, re.compile(p, re.I)) for kind, p in pats]


def _valid(name: str, brand_tokens: set) -> bool:
    n = name.strip()
    if not n or not n[0].isupper() or len(n.split()) > 3:
        return False
    low = n.lower()
    if low in _STOP or low.split()[0] in _STOP:
        return False
    if brand_tokens and set(norm_company(n).split()) & brand_tokens:  # the brand itself
        return False
    return True


def extract_competitive(items: list[dict], brand: str) -> list[dict]:
    if not brand:
        return []
    brand_tokens = set(norm_company(brand).split())
    rxs = _compiled(brand)
    seen, out = set(), []
    for it in items:
        title = (it.get("title") or "").strip()
        for kind, rx in rxs:
            m = rx.search(title)
            if not m:
                continue
            comp = m.group(1).strip(" -–—:")
            if _valid(comp, brand_tokens):
                key = (kind, comp.lower())
                if key not in seen:
                    seen.add(key)
                    out.append({"competitor": comp, "kind": kind, "title": title,
                                "url": it.get("url"), "date": it.get("date"),
                                "source": it.get("source")})
            break
    return out[:10]
