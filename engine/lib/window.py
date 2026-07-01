"""Time window + date parsing helpers."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


def make_window(today: date | None = None, days: int = 90) -> dict:
    """Trailing-`days` window ending today. Also exposes the prior period for trends."""
    today = today or date.today()
    start = today - timedelta(days=days)
    prior_start = start - timedelta(days=days)
    return {
        "today": today.isoformat(),
        "start": start.isoformat(),
        "end": today.isoformat(),
        "prior_start": prior_start.isoformat(),
        "prior_end": start.isoformat(),
        "days": days,
    }


def parse_dt(value) -> datetime | None:
    """Best-effort parse of ISO-8601, RFC-822 (RSS), or epoch-ms into an aware UTC datetime."""
    if value is None:
        return None
    # epoch milliseconds (Lever createdAt)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        except Exception:
            return None
    s = str(value).strip()
    if not s:
        return None
    # ISO-8601 (Ashby publishedAt, Greenhouse first_published, EDGAR)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    # RFC-822 (RSS pubDate)
    try:
        dt = parsedate_to_datetime(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def bucket(dt_value, window: dict) -> str:
    """Classify a date into 'in_window', 'prior', or 'out' relative to the window."""
    dt = parse_dt(dt_value)
    if dt is None:
        return "unknown"
    d = dt.date().isoformat()
    if window["start"] <= d <= window["end"]:
        return "in_window"
    if window["prior_start"] <= d < window["prior_end"]:
        return "prior"
    return "out"
