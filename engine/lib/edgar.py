"""SEC EDGAR collector — public companies only. Verified 2026-07-01."""
from __future__ import annotations

import urllib.parse

from .http import fetch_json

_TICKERS_CACHE = {"data": None}


def lookup_cik(name: str) -> dict | None:
    """Return {cik, ticker, title} if the company is public, else None."""
    if _TICKERS_CACHE["data"] is None:
        code, data = fetch_json("https://www.sec.gov/files/company_tickers.json")
        _TICKERS_CACHE["data"] = data or {}
    data = _TICKERS_CACHE["data"]
    if not data:
        return None
    n = name.lower().strip()
    # Match on company TITLE only — a bare ticker-symbol match (e.g. "ramp" == ticker RAMP)
    # collides with unrelated public companies and mis-routes private firms to EDGAR.
    for v in data.values():
        if (v.get("title") or "").lower() == n:
            return {"cik": v["cik_str"], "ticker": v["ticker"], "title": v["title"]}
    for v in data.values():  # "Datadog, Inc." startswith "datadog"
        title = (v.get("title") or "").lower()
        if title.startswith(n + " ") or title.startswith(n + ",") or title.startswith(n + " inc"):
            return {"cik": v["cik_str"], "ticker": v["ticker"], "title": v["title"]}
    return None


def collect(name: str, window: dict, cik_info: dict | None) -> dict:
    if not cik_info:
        return {"source": "edgar", "status": "skipped",
                "note": "Company not found in SEC ticker file → treated as private."}
    cik = str(cik_info["cik"])
    cik_padded = cik.zfill(10)
    filings = []
    for form in ("8-K", "10-Q", "10-K"):
        # Scope the search to THIS company's CIK so we don't pull filings from anyone
        # else who merely mentions the name.
        url = (f"https://efts.sec.gov/LATEST/search-index?q=&forms={form}&ciks={cik_padded}"
               f"&startdt={window['start']}&enddt={window['end']}")
        code, data = fetch_json(url, headers={"Accept": "application/json"})
        hits = ((data or {}).get("hits") or {}).get("hits") if isinstance(data, dict) else None
        for h in (hits or [])[:10]:
            src = h.get("_source", {})
            if cik_padded not in [str(c).zfill(10) for c in src.get("ciks", [])]:
                continue  # defensive: keep only the target company's own filings
            acc = (h.get("_id") or "").split(":")[0].replace("-", "")
            filings.append({
                "form": form,
                "date": src.get("file_date"),
                "title": (src.get("display_names") or [cik_info["title"]])[0],
                "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                       f"&CIK={cik}&type={form}",
                "accession": acc,
            })
    return {
        "source": "edgar", "status": "active" if filings else "empty",
        "cik": cik_info["cik"], "ticker": cik_info["ticker"],
        "count": len(filings),
        "note": "8-K = material events (exec/M&A/results); 10-Q = quarterly priorities+risk.",
        "signals": filings,
    }
