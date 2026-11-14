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


def month_to_date(daily, day):
    """'This month so far': days 1..day of the current month vs the same days in every earlier year.

    daily: daily VIIRS-equivalent series (harmonize.daily_reference); day: last complete day (Timestamp).
    """
    cur = day.to_period("M")
    d = daily[(daily.index.month == day.month) & (daily.index.day <= day.day)]
    s = d.groupby(d.index.year).sum()
    s.index = pd.PeriodIndex([pd.Period(f"{y}-{day.month:02d}", "M") for y in s.index])
    first_full = daily.index.min().to_period("M") + (0 if daily.index.min().day == 1 else 1)
    s = s[s.index >= first_full]
    out = month_vs_median(s, cur)
    out["through_day"] = day.day
    out["by_year"] = s
    return out


def peak_months(cal, top=3):
    return list(cal.median().sort_values(ascending=False).head(top).index)


def busiest_years(series, top=3):
    yearly = series.groupby(series.index.year).sum(min_count=1)
    full = series.groupby(series.index.year).count() == 12
    return yearly[full].sort_values(ascending=False).head(top)
