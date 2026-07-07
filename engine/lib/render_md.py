"""Deterministic markdown report from the engine JSON — the FLOOR. A user with no LLM gets
a complete, honest report; the LLM's job becomes EDIT this skeleton (check ⚠ items, tighten
prose, re-rank within reason), not compose from raw JSON. Every trust caveat survives here.
"""
from __future__ import annotations

import os

from .registry import SOURCE_ORDER

_TOP_EXCLUDE = {"tech_stack", "open_roles", "data_caveat"}
_PAID_KEYS = ("EXA_API_KEY", "FIRECRAWL_API_KEY", "PDL_API_KEY", "APIFY_API_TOKEN")


def _cite(r: dict) -> str:
    src = r.get("source") or "?"
    outlet = src.split("/", 1)[1] if "/" in src else src   # news/TechCrunch → TechCrunch
    text = f"{outlet} · {r.get('date') or 'n.d.'}"
    return f"[{text}]({r['url']})" if r.get("url") else text


def render_md(report: dict) -> str:
    w = report["window"]
    p = report["profile"]
    s = report.get("sources", {})
    sig = report.get("signals", [])
    active = report.get("sources_active", [])
    prof = ("public " + (p["ticker"] or "") if p["public"]
            else "unknown (SEC lookup failed)" if p["public"] is None else "private")
    L = [f"# Last Quarter — {p['name']} · {w['start']} → {w['end']}",
         f"**Profile:** {prof} · sources active: {', '.join(active) or 'none'} "
         f"({len(active)}/{report['sources_total']})", ""]

    # --- Top signals: top 8 by score, excluding stack/open-roles/caveats ---
    L.append("## Top signals")
    top = [r for r in sig if r["type"] not in _TOP_EXCLUDE][:8]
    if not top:
        L.append("_No ranked signals surfaced this window._")
    for i, r in enumerate(top, 1):
        warn = " ⚠ entity-check" if r["confidence"] == "low" else ""
        L.append(f"{i}. **{r['claim']}** ({_cite(r)}){warn}")
    L.append("")

    # --- By category (from per-source dicts) ---
    L.append("## By category")
    c = s.get("careers", {})
    if c.get("status") == "active":
        depts = ", ".join(f"{d}:{n}" for d, n in (c.get("dept_concentration") or [])[:4])
        L.append(f"- **Hiring:** {c['listed_total']} listed, {c['posted_in_window']} posted "
                 f"in-window{(' · ' + depts) if depts else ''}. [board]({c.get('board_url')})")
        for r in c.get("senior_roles", [])[:4]:
            L.append(f"  - Senior req: {r['title']} ({str(r.get('date') or '?')[:10]})")
        if c.get("geo_note"):
            L.append(f"  - Geo: {c['geo_note']}")
        tbc = c.get("tech_by_category") or {}
        if tbc:
            L.append("  - Stack: " + " · ".join(
                f"{k}: {', '.join(v[:5])}" for k, v in list(tbc.items())[:5]))
        for pr in c.get("priorities", [])[:2]:
            L.append(f'  - Priority: "{pr["text"]}" [{pr.get("job")}]')
        for ini in c.get("initiatives", [])[:2]:
            L.append(f'  - Initiative: "{ini["text"]}" [{ini.get("job")}]')
    ws = s.get("webstack", {})
    if ws.get("status") == "active":
        L.append("- **Observed on site:** " + " · ".join(
            f"{cat}: {', '.join(tools)}" for cat, tools in (ws.get("by_category") or {}).items()))
    pd = s.get("pdl", {})
    if pd.get("status") == "active":
        roll = ", ".join(f"{d}:{n}" for d, n in pd.get("dept_rollup", []))
        L.append(f"- **New hires (PDL, approx.):** {pd['count']} joiners · {roll}")
        for h in pd.get("senior_hires", [])[:5]:
            li = f" ({h['linkedin']})" if h.get("linkedin") else ""
            L.append(f"  - {h.get('name')} — {h.get('title')} "
                     f"({str(h.get('start') or '?')[:7]}){li}")
    b = s.get("blog", {})
    cw = b.get("customer_wins", []) if b.get("status") == "active" else []
    L.append("- **Traction:** " + (", ".join(f"customer win: {x['customer']}" for x in cw)
                                    if cw else "none surfaced in-window."))
    g = s.get("github", {})
    nr = g.get("new_repos", []) if g.get("status") == "active" else []
    if nr:
        L.append("- **Product direction:** net-new repos — " + ", ".join(r["name"] for r in nr))
    comp = [r for r in sig if r["category"] == "competitive"]
    if comp:
        L.append("- **Competitive:** " + "; ".join(r["claim"] for r in comp[:4]))
    e = s.get("edgar", {})
    if e.get("status") == "active":
        L.append("- **SEC filings:** " + ", ".join(
            f"{x['form']} ({x.get('date')})" for x in e.get("signals", [])[:4]))
    st = s.get("status", {})
    inc = st.get("signals", []) if st.get("status") == "active" else []
    L.append("- **Risk / negative:** " + ("; ".join(x["title"] for x in inc[:4])
                                          if inc else "none surfaced this window."))
    L.append("")

    # --- Coverage & confidence (every trust caveat MUST survive) ---
    L.append("## Coverage & confidence")
    L.append(f"Sources active: {len(active)} of {report['sources_total']}. Primary-sourced "
             f"claims are stated as fact; `unverified`/`low` items need an entity-check.")
    for k in SOURCE_ORDER:
        note = (s.get(k) or {}).get("note")
        if note:
            L.append(f"- **{k}:** {note}")
    missing = [key for key in _PAID_KEYS if not os.getenv(key)]
    if missing:
        L.append(f"- **Add keys to unlock more:** {', '.join(missing)}.")
    L.append("")
    L.append(report["footer"])
    return "\n".join(L)
