"""Shared identity helpers — verify entity matches against the user-supplied domain.

Root-cause fix for the wrong-entity class of bugs: CIK / GitHub-org / ATS resolution
must confirm against ground truth (the domain), not just a lexical name/slug guess.
"""
from __future__ import annotations

import re
import urllib.parse

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
