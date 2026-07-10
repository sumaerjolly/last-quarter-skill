"""Normalized signal layer — flatten every source's output into ONE uniform array so
downstream tools/AI (copy skills, enrichment pipelines) consume a stable interface
instead of our per-source schema.

Each record: {type, category, claim, date, url, source, confidence}
  category: hiring | leadership | expansion | strategy | product | traction | risk |
            tech | financial | news | discussion | competitive
  confidence: primary (company-owned/official) | unverified (3rd-party, entity-check needed)
              | low (noisy common-word news) | aggregator (labeled aggregator data)
"""
from __future__ import annotations

import re

from . import competitive
from .window import parse_dt

# Coarse ranking — a sane DEFAULT ordering (a floor, not an editor). The LLM re-ranks with
# context; this just stops the md skeleton from putting a fresh blog post above a funding
# event. Keep the tiers coarse; do not add cleverness.
_TYPE_WEIGHT = {
    "new_hire": 5, "senior_hire_req": 5, "new_initiative": 5, "customer_win": 5,
    "displacement_win": 5, "competitor_attack": 5,
    "geo_expansion": 4, "new_repo": 4, "incident": 4, "sec_filing": 4,
    "new_hires_rollup": 4, "comparison": 4,
    "news": 3, "stated_priority": 3,
    "blog_post": 2, "open_roles": 2, "hn_discussion": 2, "tech_stack": 2, "release": 2,
    "observed_stack": 2,
    "data_caveat": 1,
}
# High-stakes events buried in generic `news` → promote to weight 5.
_EVENT_HIGH = re.compile(
    r"\b(raise[sd]?|raising|funding|series [a-e]|valuation|acqui\w+|merg\w+|appoint\w+|"
    r"names? new|joins? as|steps? down|resign\w*|layoff\w*|ipo)\b", re.I)
# ...but NOT when the headline frames the event as OLD — an in-window article often just
# *mentions* a past raise ("recently raised", "last year"). Publish-date != event-date.
_STALE_EVENT = re.compile(
    r"\b(recently|previously|already|had (?:raised|closed|secured)|last year|back in|"
    r"in 20(?:2[0-5])|existing|to date|since (?:its )?found|earlier|prior|so far)\b", re.I)
_CONF_MULT = {"primary": 1.0, "unverified": 0.8, "aggregator": 0.7, "low": 0.4}
_CONF_RANK = {"primary": 3, "unverified": 2, "aggregator": 1, "low": 0}


def _recency(date_iso, window) -> float:
    """Deterministic decay against window END (never wall-clock). Undated → 0.5."""
    d = parse_dt(date_iso)
    end = parse_dt((window or {}).get("end"))
    if not d or not end:
        return 0.5
    age = (end.date() - d.date()).days
    if age <= 14:
        return 1.0
    if age <= 30:
        return 0.8
    if age <= 60:
        return 0.6
    return 0.4


def _score(rec: dict, window) -> float:
    w = _TYPE_WEIGHT.get(rec["type"], 2)
    claim = rec.get("claim") or ""
    if rec["type"] == "news" and _EVENT_HIGH.search(claim) and not _STALE_EVENT.search(claim):
        w = 5  # fresh high-stakes event; stale-worded ("recently raised") stays weight 3
    return round(w * _recency(rec["date"], window) * _CONF_MULT.get(rec["confidence"], 0.8), 2)


def _d(value):
    dt = parse_dt(value)
    return dt.date().isoformat() if dt else None


def build_signals(report: dict) -> list[dict]:
    s = report.get("sources", {})
    out: list[dict] = []

    def add(type, category, claim, source, confidence="primary", date=None, url=None):
        if claim:
            out.append({"type": type, "category": category, "claim": claim,
                        "date": date, "url": url, "source": source, "confidence": confidence})

    # --- careers ---
    c = s.get("careers", {})
    if c.get("status") == "active":
        src = f"careers/{c.get('ats')}"
        depts = ", ".join(f"{d}:{n}" for d, n in (c.get("dept_concentration") or [])[:3])
        add("open_roles", "hiring",
            f"{c.get('posted_in_window')} of {c.get('listed_total')} open roles posted in-window"
            + (f"; concentration {depts}" if depts else ""),
            src, url=c.get("board_url"))
        for r in c.get("senior_roles", []):
            add("senior_hire_req", "leadership", f"Open senior req: {r.get('title')}",
                src, date=_d(r.get("date")), url=r.get("url"))
        if c.get("geo_note"):
            add("geo_expansion", "expansion", c["geo_note"], src, url=c.get("board_url"))
        for i in c.get("initiatives", []):
            job = f" [{i.get('job')}]" if i.get("job") else ""
            add("new_initiative", "expansion", f"New initiative: {i.get('text')}{job}",
                src, url=i.get("url"))
        for p in c.get("priorities", []):
            job = f" [{p.get('job')}]" if p.get("job") else ""
            add("stated_priority", "strategy", f"Stated priority: {p.get('text')}{job}",
                src, url=p.get("url"))
        tbc = c.get("tech_by_category") or {}
        if tbc:
            flat = ", ".join(t for tools in tbc.values() for t in tools[:5])
            add("tech_stack", "tech", f"JD-mined stack: {flat[:220]}", src, url=c.get("board_url"))
        if c.get("ownership_warning"):
            add("data_caveat", "hiring", c["ownership_warning"], src, confidence="low",
                url=c.get("board_url"))

    # --- news (3rd-party outlets; entity-check needed) ---
    n = s.get("news", {})
    if n.get("status") == "active":
        conf = "low" if n.get("noisy") else "unverified"
        for it in n.get("signals", []):
            add("news", "news", it.get("title"),
                f"news/{it.get('outlet') or 'google-news'}", confidence=conf,
                date=_d(it.get("date")), url=it.get("url"))

    # --- Exa (paid): entity-resolved news, real URLs ---
    ex = s.get("exa", {})
    if ex.get("status") == "active":
        conf = "low" if ex.get("noisy") else "unverified"
        for it in ex.get("signals", []):
            add("news", "news", it.get("title"),
                f"exa/{it.get('outlet') or 'web'}", confidence=conf,
                date=_d(it.get("date")), url=it.get("url"))

    # --- blog / changelog ---
    b = s.get("blog", {})
    if b.get("status") == "active":
        for it in b.get("signals", []):
            add("blog_post", "product", it.get("title"), "blog",
                date=_d(it.get("date")), url=it.get("url"))
        for cw in b.get("customer_wins", []):
            add("customer_win", "traction", f"Case study names customer: {cw.get('customer')}",
                "blog", date=_d(cw.get("date")), url=cw.get("url"))

    # --- status / incidents ---
    st = s.get("status", {})
    if st.get("status") == "active":
        for it in st.get("signals", []):
            add("incident", "risk", f"Incident: {it.get('title')}", "status",
                date=_d(it.get("date")), url=it.get("url"))

    # --- hacker news ---
    hn = s.get("hackernews", {})
    if hn.get("status") == "active":
        for it in hn.get("signals", []):
            add("hn_discussion", "discussion", it.get("title"), "hackernews",
                confidence="unverified", date=_d(it.get("date")),
                url=it.get("discussion") or it.get("url"))

    # --- PDL (paid): actual new hires ---
    pd = s.get("pdl", {})
    if pd.get("status") == "active":
        rollup = ", ".join(f"{d}:{n}" for d, n in pd.get("dept_rollup", []))
        if rollup:
            add("new_hires_rollup", "hiring", f"Recent joiners (approx.): {rollup}",
                "pdl", confidence="aggregator")
        for h in pd.get("senior_hires", []):
            when = f" ({h['start']})" if h.get("start") else ""
            add("new_hire", "leadership", f"{h.get('name')} joined as {h.get('title')}{when}",
                "pdl", confidence="aggregator", date=_d(h.get("start")), url=h.get("linkedin"))

    # --- webstack (observed technographics) — ONE aggregated record ---
    ws = s.get("webstack", {})
    if ws.get("status") == "active":
        by_cat = ws.get("by_category") or {}
        claim = "Observed on site — " + " · ".join(
            f"{cat}: {', '.join(tools)}" for cat, tools in by_cat.items())
        # Corroboration: tools appearing in BOTH observed site AND JD-stated stack.
        careers_tech = (s.get("careers") or {}).get("tech_stack") or []
        stated = {t.get("tool", "").lower() for t in careers_tech}
        both = sorted(t for tools in by_cat.values() for t in tools if t.lower() in stated)
        if both:
            claim += f" (corroborated by JDs: {', '.join(both)})"
        add("observed_stack", "tech", claim[:240], "webstack", confidence="primary",
            url=f"https://{(report.get('profile') or {}).get('domain', '')}")

    # --- EDGAR filings ---
    e = s.get("edgar", {})
    if e.get("status") == "active":
        for it in e.get("signals", []):
            add("sec_filing", "financial", f"{it.get('form')} filed", "edgar",
                date=_d(it.get("date")), url=it.get("url"))

    # --- GitHub ---
    g = s.get("github", {})
    if g.get("status") == "active":
        for it in g.get("signals", []):
            add("release", "product", f"Release: {it.get('repo')} {it.get('name')}", "github",
                date=_d(it.get("date")), url=it.get("url"))
        for r in g.get("new_repos", []):
            desc = f": {r.get('description')}" if r.get("description") else ""
            add("new_repo", "product", f"New repo {r.get('name')}{desc}", "github",
                date=_d(r.get("created")), url=r.get("url"))

    # --- competitive dynamics (mined across blog/news/HN titles) ---
    brand = (report.get("profile") or {}).get("name") or ""
    comp_items = []
    for key in ("blog", "news", "hackernews"):
        v = s.get(key, {})
        if v.get("status") == "active":
            for it in v.get("signals", []):
                comp_items.append({"title": it.get("title"), "date": it.get("date"),
                                   "url": it.get("discussion") or it.get("url"), "source": key})
    _label = {
        "displacement_win": lambda c: f"Displacement — winning customers from {c}",
        "competitor_attack": lambda c: f"{c} launched/aimed a rival at {brand}",
        "comparison": lambda c: f"Bracketed against {c}",
    }
    for cr in competitive.extract_competitive(comp_items, brand):
        add(cr["kind"], "competitive",
            f"{_label[cr['kind']](cr['competitor'])}: {cr['title']}",
            cr["source"], confidence="primary" if cr["source"] == "blog" else "unverified",
            date=_d(cr["date"]), url=cr["url"])

    # Common-word collision propagation: if Exa (or free news) flagged the name ambiguous,
    # ALL news is collision-suspect → downgrade to low (drops it in rank + adds ⚠ marker).
    ambiguous = bool((s.get("exa") or {}).get("noisy") or (s.get("exa") or {}).get("collisions")
                     or (s.get("news") or {}).get("noisy"))
    if ambiguous:
        for r in out:
            if r["category"] == "news" and r["confidence"] != "low":
                r["confidence"] = "low"

    # Score (coarse floor), then sort: score, then confidence (primary wins ties over
    # unverified/low), then recency.
    window = report.get("window")
    for r in out:
        r["score"] = _score(r, window)
    out.sort(key=lambda x: (x["score"], _CONF_RANK.get(x["confidence"], 2),
                            x["date"] is not None, x["date"] or ""), reverse=True)
    return out
