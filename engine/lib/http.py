"""Shared HTTP helpers — stdlib only (no requests/feedparser needed)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

# SEC requires a UA with contact info; a real browser-ish UA avoids some 403s elsewhere.
UA = "last-quarter-skill/1.0 (ABM signal research; contact sumaerjolly@gmail.com)"

_LAST_HIT: dict[str, float] = {}


def _throttle(key: str, min_gap: float) -> None:
    """Block until at least min_gap seconds since the last hit for this key (e.g. GDELT)."""
    if not min_gap:
        return
    last = _LAST_HIT.get(key, 0.0)
    wait = min_gap - (time.monotonic() - last)
    if wait > 0:
        time.sleep(wait)
    _LAST_HIT[key] = time.monotonic()


def fetch(url: str, *, timeout: int = 12, headers: dict | None = None,
          throttle_key: str | None = None, min_gap: float = 0.0,
          maxbytes: int | None = None) -> tuple[int, bytes]:
    """GET a URL. Returns (status_code, body_bytes). Never raises on HTTP errors.
    maxbytes: stop reading after N bytes (e.g. just the <head> for meta tags)."""
    if throttle_key:
        _throttle(throttle_key, min_gap)
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(maxbytes) if maxbytes else resp.read()
            return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read() if hasattr(e, "read") else b""
    except Exception:
        return 0, b""


def fetch_text(url: str, **kw) -> tuple[int, str]:
    code, body = fetch(url, **kw)
    return code, body.decode("utf-8", "replace")


def fetch_json(url: str, **kw):
    """GET and parse JSON. Returns (status_code, obj_or_None)."""
    code, body = fetch(url, **kw)
    if not body:
        return code, None
    try:
        return code, json.loads(body)
    except Exception:
        return code, None
