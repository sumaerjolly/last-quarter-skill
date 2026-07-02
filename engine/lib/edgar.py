"""SEC EDGAR collector — public companies only. Verified 2026-07-01."""
from __future__ import annotations

from .http import fetch_json
from .identity import norm_company

# ok=None until first attempt; True if the ticker file loaded, False if the fetch failed.
_TICKERS_CACHE = {"data": None, "ok": None}


def tickers_ok() -> bool | None:
    """Whether the SEC ticker file loaded. None = not attempted, False = fetch failed."""
    return _TICKERS_CACHE["ok"]


def lookup_cik(name: str) -> dict | None:
    """Return {cik, ticker, title} if the company is public, else None.

    Matches on NORMALIZED company name equality (suffix/punctuation-stripped) — never a
    loose prefix or bare ticker symbol. Loose matching routed private cos to unrelated
    public filers (mercury.com -> Mercury Systems MRCY); normalized-exact prevents that
    while still matching 'Datadog' -> 'Datadog, Inc.'
    """
    if _TICKERS_CACHE["ok"] is None:
        code, data = fetch_json("https://www.sec.gov/files/company_tickers.json")
        if code == 200 and isinstance(data, dict) and data:
            _TICKERS_CACHE["data"], _TICKERS_CACHE["ok"] = data, True
        else:
            _TICKERS_CACHE["data"], _TICKERS_CACHE["ok"] = {}, False  # transport/parse fail
    data = _TICKERS_CACHE["data"]
    if not data:
        return None
    target = norm_company(name)
    if not target:
        return None
    for v in data.values():
        if norm_company(v.get("title") or "") == target:
            return {"cik": v["cik_str"], "ticker": v["ticker"], "title": v["title"]}
    return None


def collect(name: str, window: dict, cik_info: dict | None) -> dict:
    if not cik_info:
        if tickers_ok() is False:  # couldn't load the ticker file — don't claim "private"
            return {"source": "edgar", "status": "error",
                    "error": "SEC ticker file fetch failed",
                    "note": "Could not load SEC ticker file — public/private undetermined."}
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
            acc_raw, _, fname = (h.get("_id") or "").partition(":")
            acc = acc_raw.replace("-", "")
            # Direct link to the actual filing document, not a search-listing page.
            if acc and fname:
                doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{fname}"
            else:
                doc_url = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                           f"&CIK={cik}&type={form}")
            filings.append({
                "form": form,
                "date": src.get("file_date"),
                "title": (src.get("display_names") or [cik_info["title"]])[0],
                "url": doc_url,
                "accession": acc,
            })
    return {
        "source": "edgar", "status": "active" if filings else "empty",
        "cik": cik_info["cik"], "ticker": cik_info["ticker"],
        "count": len(filings),
        "note": "8-K = material events (exec/M&A/results); 10-Q = quarterly priorities+risk.",
        "signals": filings,
    }
