from __future__ import annotations

import re

from datetime import date, timedelta


# =====================================================
# NORMALIZE CITY
# =====================================================

def norm(s: str | None) -> str | None:

    if s is None:
        return None

    # убрать emoji / флаги
    s = re.sub(
        r"[^\w\s\-а-яА-ЯёЁ]",
        "",
        s
    )

    # убрать лишние пробелы
    s2 = s.strip().lower()

    return s2 if s2 else None


# =====================================================
# DATE WINDOW
# =====================================================

def make_date_window(
    center: date,
    window_days: int
) -> tuple[date, date]:

    return (
        center - timedelta(days=window_days),
        center + timedelta(days=window_days)
    )



