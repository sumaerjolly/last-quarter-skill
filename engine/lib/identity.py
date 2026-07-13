"""Shared identity helpers — verify entity matches against the user-supplied domain.

Root-cause fix for the wrong-entity class of bugs: CIK / GitHub-org / ATS resolution
must confirm against ground truth (the domain), not just a lexical name/slug guess.
"""
from __future__ import annotations

import html as _html
import re
import urllib.parse

from .http import fetch_text

# ONLY true legal-entity suffixes. NOT "systems/technologies/labs/group/holdings" —
# those are distinguishing name parts (Mercury Systems != Mercury); stripping them
# would re-introduce the wrong-entity match this whole module exists to prevent.
_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "llc", "llp",
    "ltd", "limited", "plc", "sa", "nv", "ag", "gmbh", "oy", "ab", "spa", "the",
}


def registrable_domain(value: str) -> str:
    """Best-effort registrable domain: strip scheme/www/path/port, keep last 2 labels.
    (Good enough for match checks; not a full PSL — co.uk-style TLDs are an accepted edge.)"""
    if not value:
        return ""
    v = value.strip().lower()
    if "//" not in v:
        v = "//" + v
    parts = urllib.parse.urlsplit(v)
    host = parts.netloc or parts.path
    host = host.split("@")[-1].split(":")[0].strip("/")
    if host.startswith("www."):
        host = host[4:]
    labels = [x for x in host.split(".") if x]
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def brand_slug(domain: str) -> str:
    """First label of the registrable domain: increase.com -> increase."""
    reg = registrable_domain(domain)
    return reg.split(".")[0] if reg else ""


def norm_company(s: str) -> str:
    """Normalize a company name for exact matching: lowercase, drop punctuation and
    corporate suffixes. 'Datadog, Inc.' -> 'datadog'; 'Mercury Systems Inc' -> 'mercury'."""
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    toks = [t for t in s.split() if t and t not in _SUFFIXES]
    return " ".join(toks)


# --- Brand derivation from the homepage -------------------------------------------------
# The domain slug is NOT the brand: datadoghq.com -> "Datadoghq" (not "Datadog"), trypaddle.com
# -> "Trypaddle" (not "Paddle"). A wrong name silently poisons EDGAR (public->private), news,
# Exa, HN, and the careers ownership check. Derive the real brand from the site's own metadata.
_META_TAG = re.compile(r"<meta[^>]+>", re.I)
_CONTENT = re.compile(r'content=["\']([^"\']+)["\']', re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_TITLE_SEP = re.compile(r"\s+[|–—·:]\s+")  # " | ", " – ", " — ", " · ", " : "
_BRAND_PREFIX = re.compile(r"^(get|try|join|use|hey)", re.I)


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def pick_brand(candidates: list[str], slug: str) -> str | None:
    """Pick the first candidate with SLUG AFFINITY (shares a prefix relationship with the
    domain slug), so marketing copy ('The Modern Observability Platform') can't become the
    company name. Also tries with a get/try/join/use/hey prefix stripped from either side
    (trypaddle -> paddle). Preserves the candidate's original casing. Pure/testable."""
    slug_a = _alnum(slug)
    if not slug_a:
        return None
    slug_stripped = _BRAND_PREFIX.sub("", slug_a)
    for cand in candidates:
        c = _alnum(cand)
        if len(c) < 3:
            continue
        c_stripped = _BRAND_PREFIX.sub("", c)
        for a, b in ((c, slug_a), (c, slug_stripped),
                     (c_stripped, slug_a), (c_stripped, slug_stripped)):
            if a and b and (a.startswith(b) or b.startswith(a)):
                return cand.strip()
    return None


def derive_name(domain: str) -> str | None:
    """Fetch the homepage once and derive the real brand from og:site_name / <title>,
    guarded by slug affinity. Returns None if unreachable or nothing plausible passes."""
    reg = registrable_domain(domain)
    if not reg:
        return None
    code, html = fetch_text(f"https://{reg}", maxbytes=100_000)
    if code != 200 or not html:
        return None
    candidates: list[str] = []
    for tag in _META_TAG.findall(html):  # og:site_name first — highest priority
        if "og:site_name" in tag.lower():
            m = _CONTENT.search(tag)
            if m:
                candidates.append(_html.unescape(m.group(1)).strip())
    tm = _TITLE.search(html)
    if tm:
        title = _html.unescape(re.sub(r"\s+", " ", tm.group(1)).strip())
        candidates += [seg.strip() for seg in _TITLE_SEP.split(title) if seg.strip()]
    return pick_brand(candidates, brand_slug(domain))
