"""Careers / ATS collector — Ashby, Greenhouse, Lever. Verified 2026-07-01."""
from __future__ import annotations

from collections import Counter

from .http import fetch_json
from .window import bucket


def token_candidates(domain: str, name: str | None = None) -> list[str]:
    """Guess ATS board tokens from a domain (and optional display name)."""
    base = domain.lower().replace("https://", "").replace("http://", "")
    base = base.split("/")[0]
    if base.startswith("www."):
        base = base[4:]
    slug = base.split(".")[0]  # increase.com -> increase
    cands = [slug, slug.replace("-", ""), slug.replace("-", "_")]
    if name:
        clean = "".join(c for c in name.lower() if c.isalnum())
        cands.append(clean)
    seen, out = set(), []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _ashby(token):
    code, data = fetch_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    jobs = (data or {}).get("jobs") if isinstance(data, dict) else None
    if not jobs:
        return None
    return {
        "ats": "ashby", "token": token,
        "board_url": f"https://jobs.ashbyhq.com/{token}",
        "api_url": f"https://api.ashbyhq.com/posting-api/job-board/{token}",
        "jobs": [{
            "title": j.get("title"),
            "department": j.get("department") or j.get("team"),
            "location": j.get("location"),
            "url": j.get("jobUrl"),
            "date": j.get("publishedAt"),
        } for j in jobs if j.get("isListed", True)],
    }


def _greenhouse(token):
    code, data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
    jobs = (data or {}).get("jobs") if isinstance(data, dict) else None
    if not jobs:
        return None
    return {
        "ats": "greenhouse", "token": token,
        "board_url": f"https://boards.greenhouse.io/{token}",
        "api_url": f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
        "jobs": [{
            "title": j.get("title"),
            "department": None,  # needs ?content=true / departments endpoint
            "location": (j.get("location") or {}).get("name"),
            "url": j.get("absolute_url"),
            "date": j.get("first_published") or j.get("updated_at"),
        } for j in jobs],
    }


def _lever(token):
    code, data = fetch_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    if not isinstance(data, list) or not data:  # 200 [] = dead board (verified gotcha)
        return None
    return {
        "ats": "lever", "token": token,
        "board_url": f"https://jobs.lever.co/{token}",
        "api_url": f"https://api.lever.co/v0/postings/{token}?mode=json",
        "jobs": [{
            "title": j.get("text"),
            "department": (j.get("categories") or {}).get("team")
                          or (j.get("categories") or {}).get("department"),
            "location": (j.get("categories") or {}).get("location"),
            "url": j.get("hostedUrl"),
            "date": j.get("createdAt"),
        } for j in data],
    }


def collect(domain: str, name: str | None, window: dict) -> dict:
    """Resolve the ATS board and summarize hiring signal. Careers = composition+freshness,
    NOT a clean this-90-vs-prior-90 delta (ATS returns only currently-open roles)."""
    tried = []
    board = None
    for token in token_candidates(domain, name):
        for fn in (_ashby, _greenhouse, _lever):
            board = fn(token)
            tried.append(f"{fn.__name__.strip('_')}:{token}")
            if board:
                break
        if board:
            break

    if not board:
        return {"source": "careers", "status": "empty", "tried": tried, "signals": []}

    jobs = board["jobs"]
    in_window = [j for j in jobs if bucket(j["date"], window) == "in_window"]
    dept = Counter(j["department"] for j in in_window if j.get("department"))
    return {
        "source": "careers",
        "status": "active",
        "ats": board["ats"],
        "token": board["token"],
        "board_url": board["board_url"],
        "api_url": board["api_url"],
        "listed_total": len(jobs),
        "posted_in_window": len(in_window),
        "dept_concentration": dept.most_common(6),
        "note": "ATS lists only currently-open roles (survivorship bias); read as "
                "composition + freshness, not a clean growth delta.",
        "recent_roles": [
            {"title": j["title"], "department": j.get("department"),
             "location": j.get("location"), "date": j["date"], "url": j.get("url")}
            for j in sorted(in_window, key=lambda x: str(x["date"]), reverse=True)[:15]
        ],
    }
