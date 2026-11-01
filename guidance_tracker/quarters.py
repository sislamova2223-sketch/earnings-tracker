"""Fiscal quarter labels from a filing date.

An earnings 8-K reports the quarter that ended most recently before it was filed. Companies with a
December year end are labelled "Q3 2026"; others use their fiscal year, e.g. Microsoft "FY27 Q1".
"""
from __future__ import annotations

from datetime import date


def quarter_end_before(d: date) -> date:
    """Last calendar quarter end strictly before d (filings land weeks after the quarter closes)."""
    ends = [date(d.year - 1, 12, 31), date(d.year, 3, 31), date(d.year, 6, 30), date(d.year, 9, 30), date(d.year, 12, 31)]
    return max(e for e in ends if e < d)


def fiscal_quarter(period_end: date, fy_end_month: int) -> dict:
    """Map a quarter-end date to the company's fiscal year and quarter."""
    m, y = period_end.month, period_end.year
    fy = y if m <= fy_end_month else y + 1
    q = ((m - fy_end_month - 1) % 12) // 3 + 1
    label = f"Q{q} {fy}" if fy_end_month == 12 else f"FY{fy % 100:02d} Q{q}"
    return {"fy": fy, "q": q, "label": label, "period_end": period_end.isoformat()}
