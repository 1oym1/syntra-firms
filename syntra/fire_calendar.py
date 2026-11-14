"""Burning-activity calendar and month-vs-median figures (phase 6).

Input: a monthly series with a PeriodIndex, e.g. harmonize(...)["harmonized"].
"""
import numpy as np
import pandas as pd

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def calendar(series):
    """Years x months table."""
    df = pd.DataFrame({"v": series.values, "y": series.index.year, "m": series.index.month})
    cal = df.pivot(index="y", columns="m", values="v").reindex(columns=range(1, 13))
    cal.columns = MONTHS
    cal.index.name = "year"
    return cal


def month_vs_median(series, month):
    """One month against the median of the same calendar month in all earlier years."""
    hist = series[(series.index.month == month.month) & (series.index < month)].dropna()
    value = float(series.get(month, np.nan))
    med = float(hist.median()) if len(hist) else float("nan")
    return {
        "month": str(month),
        "value": value,
        "median": med,
        "anomaly_pct": 100 * (value - med) / med if med and med > 0 else float("nan"),
        "rank": int((hist > value).sum()) + 1 if len(hist) else None,  # 1 = highest on record
        "n_years": len(hist),
        "p90": float(hist.quantile(0.9)) if len(hist) else float("nan"),
    }


def peak_months(cal, top=3):
    return list(cal.median().sort_values(ascending=False).head(top).index)


def busiest_years(series, top=3):
    yearly = series.groupby(series.index.year).sum(min_count=1)
    full = series.groupby(series.index.year).count() == 12
    return yearly[full].sort_values(ascending=False).head(top)
