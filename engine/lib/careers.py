"""Careers / ATS collector — Ashby, Greenhouse, Lever. Verified 2026-07-01."""
from __future__ import annotations

import html as _html
import re
from collections import Counter

from . import jd_mining
from .http import fetch_json, fetch_text
from .identity import brand_slug, norm_company, registrable_domain
from .window import bucket

_TAG = re.compile(r"<[^>]+>")


def _plain(s: str | None) -> str:
    """Plain text from JD HTML. UNESCAPE FIRST (Greenhouse content is entity-encoded:
    &lt;li&gt;), THEN strip the real tags — otherwise tags survive as visible <li>."""
    return _TAG.sub(" ", _html.unescape(s or ""))


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
            "text": j.get("descriptionPlain"),
        } for j in jobs if j.get("isListed", True)],
    }


def _greenhouse(token):
    # ?content=true returns departments (fixes dept-null) + full JD content.
    code, data = fetch_json(
        f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    jobs = (data or {}).get("jobs") if isinstance(data, dict) else None
    if not jobs:
        return None
    return {
        "ats": "greenhouse", "token": token,
        "company": (jobs[0].get("company_name") if jobs else None),
        "board_url": f"https://boards.greenhouse.io/{token}",
        "api_url": f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
        "jobs": [{
            "title": j.get("title"),
            "department": ((j.get("departments") or [{}])[0] or {}).get("name"),
            "location": (j.get("location") or {}).get("name"),
            "url": j.get("absolute_url"),
            "date": j.get("first_published") or j.get("updated_at"),
            "text": _plain(j.get("content")),
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
            "text": j.get("descriptionPlain") or _plain(j.get("description")),
        } for j in data],
    }


_PARSERS = {"ashby": _ashby, "greenhouse": _greenhouse, "lever": _lever}
_ATS_LINK = {
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([a-z0-9][a-z0-9-]+)", re.I),
    "greenhouse": re.compile(
        r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9]+)", re.I),
    "lever": re.compile(r"jobs\.lever\.co/([a-z0-9][a-z0-9-]+)", re.I),
}
_ATS_STOP = {"embed", "job", "job_board", "www", "for"}


def _discover_board(domain: str):
    """Fallback when slug-guessing misses: crawl the company's own careers page for its
    ATS board link. CONTAMINATION GUARD — accept only if the page references exactly ONE
    distinct board (a company's own careers page links one board; an aggregator/blog links
    many, e.g. remote.com surfaced 5 other companies' tokens)."""
    reg = registrable_domain(domain)
    for path in ("/careers", "/jobs", ""):
        code, html = fetch_text(f"https://{reg}{path}" if path else f"https://{reg}")
        if code != 200 or not html:
            continue
        cands = set()
        for prov, rx in _ATS_LINK.items():
            for tok in rx.findall(html):
                if tok.lower() not in _ATS_STOP:
                    cands.add((prov, tok.lower()))
        if len(cands) == 1:  # single board → trust it
            prov, tok = next(iter(cands))
            board = _PARSERS[prov](tok)
            if board:
                return board, f"{prov}:{tok} (discovered on /{path.strip('/') or 'home'})"
    return None, None


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

    discovered_via = None
    if not board:  # slug guesses missed — try discovering the board from /careers
        board, discovered_via = _discover_board(domain)

    if not board:
        return {"source": "careers", "status": "empty", "tried": tried, "signals": []}

    # Ownership sanity check: if the board reports a company name (Greenhouse does) that
    # shares no token with the requested name or domain slug, it may be a squatted slug.
    board_company = board.get("company")
    ownership_warn = None
    if board_company:
        bc = set(norm_company(board_company).split())
        want = set(norm_company(name or "").split()) | {brand_slug(domain)}
        if bc and want and not (bc & want):
            ownership_warn = (f"ATS board company '{board_company}' shares no name token with "
                              f"'{name}'/{brand_slug(domain)} — verify this board is theirs.")

    jobs = board["jobs"]
    in_window = [j for j in jobs if bucket(j["date"], window) == "in_window"]
    dept = Counter(j["department"] for j in in_window if j.get("department"))
    # JD mining over ALL currently-listed roles (their live stack), zero extra fetches.
    mined = jd_mining.mine(jobs, brand=name or brand_slug(domain))
    return {
        "source": "careers",
        "status": "active",
        "ats": board["ats"],
        "token": board["token"],
        "discovered_via": discovered_via,
        "board_company": board_company,
        "ownership_warning": ownership_warn,
        "board_url": board["board_url"],
        "api_url": board["api_url"],
        "listed_total": len(jobs),
        "posted_in_window": len(in_window),
        "dept_concentration": dept.most_common(6),
        "tech_stack": mined["tech_stack"][:20],
        "tech_by_category": mined["tech_by_category"],
        "priorities": mined["priorities"],
        "initiatives": mined["initiatives"],
        "note": "ATS lists only currently-open roles (survivorship bias); read as "
                "composition + freshness, not a clean growth delta. Tech stack + "
                "priorities mined from JD text (skill-context anchored).",
        "recent_roles": [
            {"title": j["title"], "department": j.get("department"),
             "location": j.get("location"), "date": j["date"], "url": j.get("url")}
            for j in sorted(in_window, key=lambda x: str(x["date"]), reverse=True)[:15]
        ],
    }
