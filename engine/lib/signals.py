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

from .window import parse_dt


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

    # dated signals first (newest first), then undated
    out.sort(key=lambda x: (x["date"] is not None, x["date"] or ""), reverse=True)
    return out
