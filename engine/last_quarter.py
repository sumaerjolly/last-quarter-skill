#!/usr/bin/env python3
"""last-quarter engine — trailing-90-day ABM signal collector for a single company.

Fires every source concurrently and emits structured JSON in seconds. A synthesis
layer (the skill / an LLM) turns this JSON into the final report.

Usage:
    python3 last_quarter.py increase.com
    python3 last_quarter.py increase.com --name "Increase" --today 2026-07-01
    python3 last_quarter.py increase.com --json > increase.json
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from lib import blog, careers, edgar, github, news
from lib.careers import token_candidates
from lib.window import make_window, parse_dt


def _fmt_date(value) -> str:
    dt = parse_dt(value)
    return dt.date().isoformat() if dt else "????-??-??"


_SYM = {"active": "✓", "empty": "✗", "error": "⚠", "skipped": "—"}


def build_footer(report: dict) -> str:
    """A verbatim coverage line the synthesized report must pass through (à la last30days)."""
    order = ["careers", "news", "blog", "edgar", "github"]
    s = report["sources"]
    parts = []
    for k in order:
        v = s.get(k, {})
        status = v.get("status", "empty")
        sym = _SYM.get(status, "✗")
        cnt = v.get("count", v.get("posted_in_window"))
        parts.append(f"{k} {sym}{f' {cnt}' if status == 'active' and cnt is not None else ''}")
    n, total = len(report["sources_active"]), report["sources_total"]
    return (f"---\n✅ sources reported back — {n}/{total} active\n"
            f"└─ {' · '.join(parts)}\n---")


def run(domain: str, name: str, today: date, use_gdelt=True, use_github=True,
        keywords: str | None = None) -> dict:
    window = make_window(today)

    # Profile & route first: EDGAR ticker lookup decides public vs private.
    cik_info = edgar.lookup_cik(name)
    profile = {
        "domain": domain, "name": name,
        "public": bool(cik_info),
        "ticker": cik_info["ticker"] if cik_info else None,
    }

    orgs = token_candidates(domain, name)
    tasks = {
        "careers": lambda: careers.collect(domain, name, window),
        "news": lambda: news.collect(name, window, use_gdelt=use_gdelt, keywords=keywords),
        "blog": lambda: blog.collect(domain, window),
        "edgar": lambda: edgar.collect(name, window, cik_info),
    }
    if use_github:
        tasks["github"] = lambda: github.collect(orgs, window)

    results = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futs = {pool.submit(fn): key for key, fn in tasks.items()}
        for fut in futs:
            key = futs[fut]
            try:
                results[key] = fut.result(timeout=40)
            except Exception as e:
                results[key] = {"source": key, "status": "error", "error": str(e)}

    active = [k for k, v in results.items() if v.get("status") == "active"]
    report = {
        "window": window,
        "profile": profile,
        "sources_active": active,
        "sources_total": len(tasks),
        "sources": results,
    }
    report["footer"] = build_footer(report)
    return report


def compact(report: dict) -> str:
    w, p = report["window"], report["profile"]
    L = [f"🗓  last-quarter · {p['name']} ({p['domain']})  ·  {w['start']} → {w['end']}",
         f"    profile: {'public ' + (p['ticker'] or '') if p['public'] else 'private'}"
         f"  ·  sources active: {len(report['sources_active'])}/{report['sources_total']}"
         f" ({', '.join(report['sources_active']) or 'none'})", ""]
    s = report["sources"]
    c = s.get("careers", {})
    if c.get("status") == "active":
        L.append(f"  HIRING  {c['ats']} · {c['listed_total']} listed, "
                 f"{c['posted_in_window']} posted in-window · "
                 f"{', '.join(f'{d}:{n}' for d, n in c.get('dept_concentration', [])[:4])}")
        for r in c.get("recent_roles", [])[:5]:
            L.append(f"          - {_fmt_date(r.get('date'))} "
                     f"{r['title']} [{r.get('department') or ''}]")
    for key, label in (("blog", "LAUNCH/BLOG"), ("news", "NEWS"),
                       ("edgar", "EDGAR"), ("github", "GITHUB")):
        v = s.get(key, {})
        if v.get("status") == "active":
            flag = "  ⚠ noisy" if v.get("noisy") else ""
            L.append(f"  {label}  {v.get('count', 0)} in-window{flag}")
            for it in v.get("signals", [])[:4]:
                t = it.get("title") or it.get("name") or it.get("form")
                L.append(f"          - {_fmt_date(it.get('date'))} {t}")
            if v.get("note"):
                L.append(f"          ↳ {v['note']}")
        elif v.get("status") in ("empty", "skipped") and v.get("note"):
            L.append(f"  {label}  ({v['status']}) {v['note']}")
    L.append("")
    L.append(report["footer"])
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--name", help="Display name (default: derived from domain)")
    ap.add_argument("--today", help="Override today (YYYY-MM-DD) for the window")
    ap.add_argument("--keywords", help="Disambiguating news terms for common-word names, "
                                       'e.g. "fintech OR banking OR payments"')
    ap.add_argument("--json", action="store_true", help="Emit raw JSON")
    ap.add_argument("--no-gdelt", action="store_true")
    ap.add_argument("--no-github", action="store_true")
    a = ap.parse_args()

    dom = a.domain.replace("https://", "").replace("http://", "").split("/")[0]
    name = a.name or dom.split(".")[0].replace("-", " ").title()
    today = date.fromisoformat(a.today) if a.today else date.today()

    report = run(dom, name, today, use_gdelt=not a.no_gdelt, use_github=not a.no_github,
                 keywords=a.keywords)
    if a.json:
        json.dump(report, sys.stdout, indent=2, default=str)
        print()
    else:
        print(compact(report))


if __name__ == "__main__":
    main()
