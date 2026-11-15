"""Analyses the app shows, as plain functions (backend for app/, scripts and slide figures).

Everything here starts from the harmonized record that syntra.harmonize writes, in the same unit
(fire-active 0.1 degree cell-days, VIIRS S-NPP equivalent), so the app, the scripts and the slides
always show the same numbers.

    from syntra import analysis, datapack
    pack = datapack.load("Sudan")
    analysis.summary(pack)                 # status card, month so far, KPIs, next month
    daily = analysis.daily_series(pack["celldays"], pack["factors"])
    analysis.risk_periods(daily)           # when fire activity is usually highest

Thresholds below are team choices, not standard values (see docs/DECISIONS.md).
"""
import numpy as np
import pandas as pd

from syntra import harmonize as hz
from syntra.clean import SENSOR_START

# ---------------------------------------------------------------- thresholds (one place)
VERY_HIGH_PCTL = 90      # above the 90th percentile of the same month in earlier years -> Very high
NORMAL_BAND = 20         # within +/-20 % of the median of the same month -> Normal
HIGH_WEEK_PCTL = 75      # a week has "high activity" at or above this percentile of all weeks
RISK_CLASSES = [(75, "Extreme"), (50, "High"), (25, "Moderate"), (0, "Low")]   # % of years with a high week
STATUS_ICON = {"Very high": "🔴", "Above normal": "🟠", "Normal": "🟢", "Below normal": "🔵",
               "No baseline yet": "⚪"}

VIIRS_START = pd.Timestamp(year=SENSOR_START["VIIRS"][0], month=SENSOR_START["VIIRS"][1], day=1)
MODIS_START = pd.Timestamp(year=SENSOR_START["MODIS"][0], month=SENSOR_START["MODIS"][1], day=1)
AQUA_START = pd.Timestamp(year=hz.AQUA_START // 100, month=hz.AQUA_START % 100, day=1)


# ---------------------------------------------------------------- monthly record
def monthly(series):
    """harmonized_<country>.csv -> Series of harmonized cell-days indexed by month (pd.Period)."""
    idx = pd.PeriodIndex([pd.Period(year=int(y), month=int(m), freq="M")
                          for y, m in zip(series.year, series.month)])
    return pd.Series(series.harmonized_cells.to_numpy(float), index=idx, name="harmonized_cells")


def compare(value, history):
    """One value against earlier values of the same month (or the same days of it)."""
    hist = pd.Series(history, dtype=float).dropna()
    med = float(hist.median()) if len(hist) else np.nan
    return {"value": float(value), "median": med,
            "anomaly_pct": 100 * (value - med) / med if med and med > 0 else np.nan,
            "rank": int((hist > value).sum()) + 1 if len(hist) else None,      # 1 = highest on record
            "n_years": len(hist) + 1,
            "p90": float(hist.quantile(VERY_HIGH_PCTL / 100)) if len(hist) else np.nan}


def status(c):
    """Plain-language status, checked in this order:
    above the 90th percentile -> Very high; >= +20 % vs median -> Above normal;
    <= -20 % -> Below normal; otherwise Normal."""
    a = c["anomaly_pct"]
    if not np.isfinite(a):
        return "No baseline yet"
    if np.isfinite(c["p90"]) and c["value"] > c["p90"]:
        return "Very high"
    if a >= NORMAL_BAND:
        return "Above normal"
    if a <= -NORMAL_BAND:
        return "Below normal"
    return "Normal"


def month_vs_median(s, month):
    """A full month against the same calendar month in every earlier year."""
    hist = s[(s.index.month == month.month) & (s.index < month)]
    c = compare(s.get(month, np.nan), hist.values)
    c.update(month=str(month), status=status(c))
    return c


def month_to_date(celldays, factors, last_day=None):
    """Days 1..D of the latest month against the same days of that month in every earlier year.

    Uses harmonize.harmonize_area on the same days, so it follows the exact harmonization rules.
    """
    last_day = pd.Timestamp(last_day or celldays.acq_date.max())
    same = celldays[(celldays.month == last_day.month) & (celldays.acq_date.dt.day <= last_day.day)]
    tab = hz.harmonize_area(same, factors["terra_to_terra_aqua"], factors["modis_to_viirs"])
    tab = tab[(tab.month == last_day.month) & (tab.modis_flying | tab.viirs_flying)]
    by_year = tab.set_index("year")["harmonized_cells"]
    now = float(by_year.get(last_day.year, 0.0))
    c = compare(now, by_year.drop(last_day.year, errors="ignore").values)
    c.update(last_day=last_day, days=last_day.day, status=status(c), by_year=by_year)
    return c


def year_to_date(s, last_month):
    """Jan..last_month total of this year vs the median of the same months in earlier full years."""
    cal = calendar(s)
    part = cal.loc[:, :last_month.month]
    past = part[(part.index < last_month.year)].dropna()
    now = float(part.loc[last_month.year].sum()) if last_month.year in part.index else np.nan
    c = compare(now, past.sum(axis=1).values)
    c.update(status=status(c))
    return c


def calendar(s):
    """Years x months (1..12) table of harmonized cell-days."""
    df = pd.DataFrame({"v": s.values, "y": s.index.year, "m": s.index.month})
    return df.pivot(index="y", columns="m", values="v").reindex(columns=range(1, 13))


def annual_totals(s):
    """Totals of complete years only (12 months of data)."""
    cal = calendar(s).dropna()
    return cal.sum(axis=1)


def trend(annual):
    """OLS trend of yearly totals: slope per year, % of the mean per decade, R2 (for orientation only)."""
    x = annual.index.to_numpy(float)
    y = annual.to_numpy(float)
    b, a = np.polyfit(x, y, 1)
    fit = a + b * x
    r2 = 1 - ((y - fit) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return {"slope_per_year": float(b), "pct_per_decade": float(100 * 10 * b / y.mean()), "r2": float(r2),
            "fit": pd.Series(fit, index=annual.index)}


def next_month_usually(s, month):
    """What the coming calendar month usually brings (climatology from past years, not a forecast)."""
    nxt = month + 1
    hist = s[(s.index.month == nxt.month) & (s.index < month)].dropna()
    this = s[(s.index.month == month.month) & (s.index < month)].dropna()
    ratio = (hist.median() / this.median()) if len(this) and this.median() > 0 else np.nan
    return {"month": nxt.strftime("%b"), "median": float(hist.median()),
            "p10": float(hist.quantile(0.1)), "p90": float(hist.quantile(0.9)),
            "change_vs_this_month_pct": float(100 * (ratio - 1)) if np.isfinite(ratio) else np.nan}


# ---------------------------------------------------------------- daily record (weeks, risk periods)
def daily_series(celldays, factors, last_day=None):
    """Harmonized fire cell-days per day, from the first MODIS day to the last full day of data.

    Same rules as syntra.harmonize: VIIRS observed from its first full month, MODIS x the monthly
    MODIS -> VIIRS factor before that (x the Terra -> Terra+Aqua factor before Aqua). Summing a
    month of this series gives the monthly harmonized value exactly.
    """
    last_day = pd.Timestamp(last_day or celldays.acq_date.max())
    days = pd.date_range(MODIS_START, last_day, freq="D")

    def per_day(rows):
        return rows.drop_duplicates(["acq_date", "cell_id"]).groupby("acq_date").size().reindex(days, fill_value=0)

    modis = per_day(celldays[celldays.family == "MODIS"])
    viirs = per_day(celldays[celldays.family == "VIIRS"])
    m = days.month
    k_v = factors["modis_to_viirs"].reindex(range(1, 13)).to_numpy()[m - 1]
    k_t = np.where(days < AQUA_START, factors["terra_to_terra_aqua"].reindex(range(1, 13)).to_numpy()[m - 1], 1.0)
    out = pd.Series(modis.to_numpy() * k_v * k_t, index=days, name="harmonized_cells")
    use_viirs = days >= VIIRS_START
    out[use_viirs] = viirs[use_viirs].to_numpy(float)
    return out


def weekly(daily):
    """Years x 52 weeks of the year, cell-days per 7 days (complete weeks only; week 52 has 8-9 days)."""
    d = daily.to_frame("v")
    d["year"], d["wk"] = d.index.year, np.minimum((d.index.dayofyear - 1) // 7, 51)
    g = d.groupby(["year", "wk"]).v.agg(["sum", "count"])
    g = g[g["count"] >= 7]
    return (g["sum"] * 7 / g["count"]).unstack()


def _week_label(w, origin=0):
    return (pd.Timestamp("2001-01-01") + pd.Timedelta(days=7 * ((w + origin) % 52))).strftime("%d %b")


def risk_periods(daily, q=HIGH_WEEK_PCTL, years=None):
    """When fire activity has usually been highest, week by week of the year.

    A week of a given year is "high activity" when its cell-days reach the q-th percentile of all
    weeks in the chosen full years. Each week of the year gets the share of years in which it was
    high, and a class (Extreme >= 75 %, High >= 50 %, Moderate >= 25 %, else Low).
    Also returns, per fire year, the first and last high week and the number of high weeks.
    """
    wk = weekly(daily)
    last = daily.index.max()
    full = [y for y in wk.index if MODIS_START.year < y < last.year]
    if years:
        full = [y for y in full if years[0] <= y <= years[1]]
    base = wk.loc[full]
    thr = float(np.nanpercentile(base.values, q))
    freq = 100 * (base >= thr).mean()
    cuts = sorted(t for t, _ in RISK_CLASSES)
    cls = pd.cut(freq, [-1] + cuts[1:] + [101], labels=[n for _, n in sorted(RISK_CLASSES)], right=False)

    # Runs of consecutive weeks in the highest class present (a run may wrap over New Year)
    top = next((c for c in ("Extreme", "High", "Moderate") if (cls == c).any()), None)
    periods = []
    if top:
        on = (cls == top).to_numpy()
        runs, start = [], None
        for w in range(52):
            if on[w] and start is None:
                start = w
            if (not on[w] or w == 51) and start is not None:
                runs.append([start, w if on[w] else w - 1])
                start = None
        if len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == 51:
            runs[0][0] = runs[-1][0] - 52
            runs.pop()
        for a, b in runs:
            ws = [w % 52 for w in range(a, b + 1)]
            end = pd.Timestamp("2001-01-01") + pd.Timedelta(days=7 * (b % 52) + 6)
            periods.append({"class": top, "start": _week_label(a), "end": f"{end:%d %b}",
                            "weeks": len(ws), "share_of_years_pct": float(freq.iloc[ws].mean())})
        periods.sort(key=lambda p: -p["share_of_years_pct"])

    # Season per fire year: a fire year starts at the usually quietest week, so a season over New Year stays whole
    origin = int(base.median().to_numpy().argmin())
    rows = []
    for y in wk.index:
        nxt = wk.loc[y + 1].iloc[:origin] if y + 1 in wk.index else pd.Series(np.nan, index=range(origin))
        seq = pd.concat([wk.loc[y].iloc[origin:], nxt]) if origin else wk.loc[y]
        seq = seq.to_numpy(float)
        if np.isnan(seq).any():
            continue
        hi = np.where(seq >= thr)[0]
        if len(hi):
            rows.append({"fire_year": f"{y}/{str(y + 1)[2:]}" if origin else str(y), "year": y,
                         "first_high_week": _week_label(hi[0], origin), "last_high_week": _week_label(hi[-1], origin),
                         "high_weeks": len(hi)})
    seasons = pd.DataFrame(rows)
    growth = float(10 * np.polyfit(seasons.year, seasons.high_weeks, 1)[0]) if len(seasons) >= 5 else np.nan
    weeks = pd.DataFrame({"week_start": [_week_label(w) for w in range(52)], "share_of_years_pct": freq.to_numpy(),
                          "class": cls.astype(str).to_numpy(), "median": base.median().to_numpy(),
                          "p90": base.quantile(0.9).to_numpy()})
    return {"threshold": thr, "q": q, "years": (min(full), max(full)), "weeks": weeks, "periods": periods,
            "seasons": seasons, "high_weeks_per_decade": growth}


# ---------------------------------------------------------------- everything for the header
def summary(pack):
    """Status card, month so far, year to date, KPIs and next month, from a datapack."""
    s = monthly(pack["series"])
    mtd = month_to_date(pack["celldays"], pack["factors"])
    last_day = mtd["last_day"]
    cur = pd.Period(last_day, freq="M")
    last_full = cur - 1 if last_day < last_day + pd.offsets.MonthEnd(0) else cur
    annual = annual_totals(s)
    cal = calendar(s)
    return {
        "data_to": last_day,
        "month_so_far": mtd,
        "last_full_month": month_vs_median(s, last_full),
        "year_to_date": year_to_date(s[s.index <= last_full], last_full),
        "busiest_year": (int(annual.idxmax()), float(annual.max())),
        "peak_months": [pd.Timestamp(2001, m, 1).strftime("%b") for m in cal.median().sort_values(ascending=False).index[:3]],
        "trend": trend(annual),
        "next_month": next_month_usually(s, cur),
    }
