"""GitHub releases collector — dev-tool companies only. Best-effort, unauthenticated."""
from __future__ import annotations

import os

from .http import fetch_json
from .window import bucket

_HDRS = {"Accept": "application/vnd.github+json"}
if os.getenv("GITHUB_TOKEN"):
    _HDRS["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"


def collect(org_candidates: list[str], window: dict) -> dict:
    org = None
    repos = None
    for cand in org_candidates:
        code, data = fetch_json(
            f"https://api.github.com/orgs/{cand}/repos?sort=pushed&per_page=15",
            headers=_HDRS)
        if code == 200 and isinstance(data, list) and data:
            org, repos = cand, data
            break
    if not repos:
        return {"source": "github", "status": "empty",
                "note": "No public GitHub org matched — skip for non-dev companies."}
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

    from collections import Counter
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
