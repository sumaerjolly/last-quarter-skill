"""Customer-win extraction from blog/case-study TITLES → Traction signal. A named customer
in a case-study title is a new logo (reference selling, momentum). Precision-first: match
title SHAPES, guard against generic words and the company's own name."""
from __future__ import annotations

import re

from .identity import norm_company

# Company-name capture group: must START uppercase (proper noun), <=~30 chars.
_CO = r"([A-Z][A-Za-z0-9&.'\- ]{1,30}?)"
_PATTERNS = [
    re.compile(rf"^How {_CO} (?:built|uses?|used|scaled|grew|achieved|automated|saved|"
               rf"increased|reduced|cut|transformed|streamlined|improved|drove|boosted|"
               rf"switched|went|generat\w+|launch\w+|doubl\w+|tripl\w+)", re.I),
    # name runs to the end / a separator / a following lowercase word — bound the lazy capture
    re.compile(r"^(?:Case Study|Customer Story|Customer Spotlight)\s*[:\-–]\s*"
               r"([A-Z][A-Za-z0-9&.'\- ]{1,40}?)(?=$|\s*[:\-–|]|\s+[a-z])", re.I),
    re.compile(rf"{_CO}\s+(?:Customer Story|Case Study)$", re.I),
    re.compile(rf"^Why {_CO} (?:chose|switched to|picked|moved to|uses|left)", re.I),
]

_STOP = {"we", "i", "you", "your", "our", "the", "this", "that", "it", "ai", "llm", "llms",
         "marketers", "teams", "companies", "brands", "leaders", "one", "many", "most",
         "top", "how", "why", "to", "a", "an", "content", "customers", "startups", "founders"}


def _valid(name: str, brand_tokens: set) -> bool:
    n = name.strip()
    if not n or not n[0].isupper():        # must be a proper noun
        return False
    if len(n.split()) > 4:                  # too long to be a company name
        return False
    low = n.lower()
    if low in _STOP or low.split()[0] in _STOP:
        return False
    if brand_tokens and set(norm_company(n).split()) & brand_tokens:  # the company itself
        return False
    return True


def extract_customer_wins(items: list[dict], brand: str | None = None) -> list[dict]:
    brand_tokens = set(norm_company(brand or "").split())
    seen, out = set(), []
    for it in items:
        title = (it.get("title") or "").strip()
        for rx in _PATTERNS:
            m = rx.search(title)
            if not m:
                continue
            name = m.group(1).strip(" -–—:")
            if _valid(name, brand_tokens) and name.lower() not in seen:
                seen.add(name.lower())
                out.append({"customer": name, "title": title,
                            "url": it.get("url"), "date": it.get("date")})
            break
    return out[:8]
