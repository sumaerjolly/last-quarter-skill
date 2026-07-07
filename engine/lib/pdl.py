"""PeopleDataLabs collector (paid, PDL_API_KEY) — recent new hires (the signal free can't
get). Free careers shows only OPEN roles (survivorship bias); PDL shows PEOPLE who actually
joined: named senior hires (with LinkedIn) + a "Sales +6, Eng +3" dept rollup.

Domain-anchored (job_company_website) → entity-precise, no name-collision problem.
COST-CAPPED: size=20 (PDL bills 1 credit per returned record), one call per run, key-gated.
Month-precision + PDL is batch data that lags — labeled "recent joiners (approx.)".
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import date, timedelta

from .http import post_json
from .identity import registrable_domain

API = "https://api.peopledatalabs.com/v5/person/search"
_SENIOR_LEVELS = {"cxo", "vp", "director", "owner", "partner"}
_SENIOR_TITLE = ("head of", "chief", "founder", "vp ", "vice president", "president")
_MAX = 20  # <= 20 credits per run


def available() -> bool:
    return bool(os.getenv("PDL_API_KEY"))


def _is_senior(levels: set, title: str) -> bool:
    return bool(levels & _SENIOR_LEVELS) or any(w in title.lower() for w in _SENIOR_TITLE)


def collect(name: str, domain: str, window: dict) -> dict:
    key = os.getenv("PDL_API_KEY")
    if not key:
        return {"source": "pdl", "status": "skipped", "note": "no PDL_API_KEY set"}
    reg = registrable_domain(domain)
    # widen ~30 days earlier than the report window to offset PDL's detection/batch lag
    gte = (date.fromisoformat(window["start"]) - timedelta(days=30)).isoformat()
    body = {
        "query": {"bool": {"must": [
            {"term": {"job_company_website": reg}},
            {"range": {"job_start_date": {"gte": gte}}},
        ]}},
        "size": _MAX,
    }
    code, data = post_json(API, body, headers={"X-Api-Key": key})
    if code == 401:
        return {"source": "pdl", "status": "error", "error": "PDL 401 — bad PDL_API_KEY",
                "note": "PDL rejected the key."}
    if code in (402, 429) or (isinstance(data, dict) and data.get("status") in (402, 429)):
        return {"source": "pdl", "status": "error",
                "note": "PDL quota/credits exhausted or rate-limited."}
    if code == 0 or not isinstance(data, dict):
        return {"source": "pdl", "status": "error", "error": f"PDL unreachable (code {code})",
                "note": "PDL fetch failed — not confirmed empty."}
    people = data.get("data") or []

    rollup = Counter()
    seniors = []
    for p in people:
        role = ((p.get("job_title_role") or "other").replace("_", " ").title())
        rollup[role] += 1
        levels = set(p.get("job_title_levels") or [])
        title = p.get("job_title") or ""
        if _is_senior(levels, title):
            seniors.append({
                "name": p.get("full_name"), "title": title, "dept": role,
                "seniority": sorted(levels), "start": p.get("job_start_date"),
                "linkedin": p.get("linkedin_url"), "prior": p.get("job_company_name"),
            })
    seniors.sort(key=lambda x: str(x.get("start") or ""), reverse=True)
    return {
        "source": "pdl", "status": "active" if people else "empty",
        "count": len(people), "credits_used": len(people),
        "dept_rollup": rollup.most_common(),
        "senior_hires": seniors[:10],
        "note": (f"Recent joiners (approx., month-precision; PDL is batch data that lags — "
                 f"widened to {gte}). Free careers can't show actual hires."),
    }
