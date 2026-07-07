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

from lib import edgar
from lib.careers import token_candidates
from lib.registry import SOURCE_ORDER, SOURCES, Ctx
from lib.signals import build_signals
from lib.window import make_window, parse_dt


def _fmt_date(value) -> str:
    dt = parse_dt(value)
    return dt.date().isoformat() if dt else "????-??-??"


_SYM = {"active": "✓", "empty": "✗", "error": "⚠", "skipped": "—"}


def build_footer(report: dict) -> str:
    """A verbatim coverage line the synthesized report must pass through (à la last30days).
    `—` = not applicable (routed off / disabled by flag) and excluded from the denominator;
    `⚠` = probed but errored; `✗` = probed and empty; `✓ N` = active with count."""
    s = report["sources"]
    parts, attempted, active = [], 0, 0
    for k in SOURCE_ORDER:
        if k not in s or s[k].get("status") == "skipped":
            parts.append(f"{k} —")  # not run / routed off — not counted
            continue
        v = s[k]
        status = v.get("status", "empty")
        attempted += 1
        if status == "active":
            active += 1
        cnt = v.get("count", v.get("posted_in_window"))
        show = f" {cnt}" if status == "active" and cnt is not None else ""
        parts.append(f"{k} {_SYM.get(status, '✗')}{show}")
    return (f"---\n✅ sources reported back — {active}/{attempted} applicable\n"
            f"└─ {' · '.join(parts)}\n---")


def run(domain: str, name: str, today: date, use_gdelt=True, use_github=True,
        keywords: str | None = None) -> dict:
    window = make_window(today)

    # Profile & route first: EDGAR ticker lookup decides public vs private.
    cik_info = edgar.lookup_cik(name)
    # If the SEC ticker file failed to load, public/private is UNKNOWN — don't claim private.
    public = None if edgar.tickers_ok() is False else bool(cik_info)
    profile = {
        "domain": domain, "name": name,
        "public": public,
        "ticker": cik_info["ticker"] if cik_info else None,
    }

    ctx = Ctx(domain=domain, name=name, window=window, cik_info=cik_info,
              orgs=token_candidates(domain, name), keywords=keywords,
              use_gdelt=use_gdelt, use_github=use_github)
    active_sources = [s for s in SOURCES if s.applies(ctx)]

    results = {}
    with ThreadPoolExecutor(max_workers=max(1, len(active_sources))) as pool:
        futs = {pool.submit(src.run, ctx): src.key for src in active_sources}
        for fut in futs:
            key = futs[fut]
            try:
                results[key] = fut.result(timeout=40)
            except Exception as e:
                results[key] = {"source": key, "status": "error",
                                "error": str(e) or type(e).__name__}

    active = [k for k, v in results.items() if v.get("status") == "active"]
    report = {
        "window": window,
        "profile": profile,
        "sources_active": active,
        "sources_total": len(active_sources),
        "sources": results,
    }
    report["footer"] = build_footer(report)
    report["signals"] = build_signals(report)  # normalized flat interface for downstream tools
    return report


def compact(report: dict) -> str:
    w, p = report["window"], report["profile"]
    prof = ("public " + (p["ticker"] or "") if p["public"]
            else "unknown (SEC lookup failed)" if p["public"] is None else "private")
    L = [f"🗓  last-quarter · {p['name']} ({p['domain']})  ·  {w['start']} → {w['end']}",
         f"    profile: {prof}", ""]
    s = report["sources"]
    c = s.get("careers", {})
    if c.get("status") == "active":
        L.append(f"  HIRING  {c['ats']} · {c['listed_total']} listed, "
                 f"{c['posted_in_window']} posted in-window · "
                 f"{', '.join(f'{d}:{n}' for d, n in c.get('dept_concentration', [])[:4])}")
        if c.get("ownership_warning"):
            L.append(f"          ⚠ {c['ownership_warning']}")
        for r in c.get("senior_roles", [])[:4]:
            L.append(f"  SENIOR  - {_fmt_date(r.get('date'))} {r['title']} "
                     f"[{r.get('department') or ''}]")
        cats = c.get("tech_by_category") or {}
        if cats:
            L.append("  STACK   " + "  ·  ".join(
                f"{cat}: {', '.join(tools[:6])}" for cat, tools in list(cats.items())[:5]))
        if c.get("geo_note"):
            L.append(f"  GEO     {c['geo_note']}")
        for i in c.get("initiatives", [])[:2]:
            L.append(f"  NEW-INIT  \"{i['text']}\"  [{i['job']}]")
        for p in c.get("priorities", [])[:2]:
            L.append(f"  PRIORITY  \"{p['text']}\"  [{p['job']}]")
        for r in c.get("recent_roles", [])[:5]:
            L.append(f"          - {_fmt_date(r.get('date'))} "
                     f"{r['title']} [{r.get('department') or ''}]")
    for key, label in (("blog", "LAUNCH/BLOG"), ("exa", "NEWS(Exa)"), ("news", "NEWS(free)"),
                       ("status", "RISK/STATUS"), ("hackernews", "HN"),
                       ("edgar", "EDGAR"), ("github", "GITHUB")):
        v = s.get(key, {})
        if v.get("status") == "active":
            flag = "  ⚠ noisy" if v.get("noisy") else ""
            L.append(f"  {label}  {v.get('count', 0)} in-window{flag}")
            for it in v.get("signals", [])[:4]:
                t = it.get("title") or it.get("name") or it.get("form")
                L.append(f"          - {_fmt_date(it.get('date'))} {t}")
            for nr in v.get("new_repos", [])[:5]:
                L.append(f"          + NEW REPO {_fmt_date(nr.get('created'))} "
                         f"{nr['name']} — {nr.get('description') or ''}")
            if v.get("customer_wins"):
                L.append("          ↳ CUSTOMERS (case studies): "
                         + ", ".join(cw["customer"] for cw in v["customer_wins"]))
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
