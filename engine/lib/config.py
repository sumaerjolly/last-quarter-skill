"""Auto-load API keys from a .env file so OSS users don't touch their shell profile.

Load order (first hit wins per key; a key already in the REAL environment is never
overwritten): $LAST_QUARTER_ENV → ./.env (engine + skill dir) → ~/.config/last-quarter/.env
"""
from __future__ import annotations

import os
from pathlib import Path

KEYS = ("EXA_API_KEY", "FIRECRAWL_API_KEY", "PDL_API_KEY", "APIFY_API_TOKEN", "GITHUB_TOKEN")


def _parse(path: Path) -> dict:
    out = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip("'\"")
            if k:
                out[k] = v
    except Exception:
        pass
    return out


def load_env() -> None:
    engine = Path(__file__).resolve().parent.parent  # engine/
    override = os.getenv("LAST_QUARTER_ENV")
    if override:
        candidates = [Path(override)]  # explicit override → ONLY that file (even if empty)
    else:
        candidates = [engine / ".env", engine.parent / ".env",
                      Path.home() / ".config" / "last-quarter" / ".env"]
    for path in candidates:
        for k, v in _parse(path).items():
            if v and not os.getenv(k):  # real env vars + earlier files win
                os.environ[k] = v
