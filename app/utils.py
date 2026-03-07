from __future__ import annotations
from datetime import date, timedelta


def norm(s: str | None) -> str | None:
    if s is None:
        return None
    s2 = s.strip()
    return s2 if s2 else None


def make_date_window(center: date, window_days: int) -> tuple[date, date]:
    return (center - timedelta(days=window_days), center + timedelta(days=window_days))