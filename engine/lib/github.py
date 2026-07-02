"""GitHub releases collector — dev-tool companies only. Best-effort, unauthenticated."""
from __future__ import annotations

import os
from collections import Counter

from .http import fetch_json
from .identity import registrable_domain
from .window import bucket

_HDRS = {"Accept": "application/vnd.github+json"}
if os.getenv("GITHUB_TOKEN"):
    _HDRS["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"


def _resolve_org(candidates: list[str], domain: str):
    """Find a GitHub org and VERIFY it belongs to the domain (org.blog host == domain).
    Returns (org_login, repos, status). Prevents slug-squat matches like orgs/notion ->
    an unrelated org 'Trove'. Returns status 'error' if the lookups hit a transport failure."""
    want = registrable_domain(domain)
    saw_response = False
    for cand in candidates:
        code, org = fetch_json(f"https://api.github.com/orgs/{cand}", headers=_HDRS)
        if code == 0:
            continue  # transport error on this candidate; try the next
        saw_response = True
        if code != 200 or not isinstance(org, dict):
            continue  # 404 / rate-limited body
        blog = registrable_domain(org.get("blog") or "")
        if not (blog and want and blog == want):
            continue  # org exists but is NOT verifiably this company's — refuse it
        login = org.get("login") or cand
        code2, repos = fetch_json(
            f"https://api.github.com/orgs/{login}/repos?sort=pushed&per_page=15",
            headers=_HDRS)
        if isinstance(repos, list) and repos:
            return login, repos, "ok"
    return None, None, ("error" if not saw_response else "empty")


def collect(org_candidates: list[str], window: dict, domain: str) -> dict:
    org, repos, status = _resolve_org(org_candidates, domain)
    if not repos:
        if status == "error":
            return {"source": "github", "status": "error",
                    "error": "GitHub API unreachable",
                    "note": "GitHub lookups failed (network/rate-limit) — not confirmed empty."}
        return {"source": "github", "status": "empty",
                "note": "No GitHub org verifiably owned by this domain (org.blog must match) "
                        "— skipped to avoid a wrong-entity match."}
    releases = []
    for repo in repos[:8]:
        name = repo.get("name")
        code, rels = fetch_json(
            f"https://api.github.com/repos/{org}/{name}/releases?per_page=10",
            headers=_HDRS)
        for r in (rels or []) if isinstance(rels, list) else []:
            if bucket(r.get("published_at"), window) == "in_window":
                releases.append({
                    "repo": name, "name": r.get("name") or r.get("tag_name"),
                    "date": r.get("published_at"), "url": r.get("html_url"),
                })
    releases.sort(key=lambda x: str(x["date"]), reverse=True)

    by_repo = Counter(r["repo"] for r in releases)
    # Auto-generated SDK repos publish dozens of version bumps → cadence, not launches.
    sdk_like = sum(n for repo, n in by_repo.items()
                   if any(k in repo.lower() for k in ("sdk", "-python", "-node", "-go",
                          "-java", "-ruby", "-php", "-typescript", "-api", "openapi")))
    note = None
    if sdk_like and sdk_like >= 0.5 * len(releases):
        note = (f"{sdk_like}/{len(releases)} releases are automated SDK version bumps "
                f"(cadence signal of active API dev, not discrete product launches).")
    return {
        "source": "github", "status": "active" if releases else "empty",
        "org": org, "count": len(releases),
        "repos_active": by_repo.most_common(8), "note": note,
        "signals": releases[:12],
    }
