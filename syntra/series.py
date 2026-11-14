"""The app's monthly series: syntra.harmonize (Steps 4-5) extended to 2026.

Unit everywhere: the one syntra.harmonize uses (hz.COUNT: fire-active 0.1 degree cell-days per month by
default), in VIIRS S-NPP units.

What this adds on top of syntra.harmonize
1. Month spans from the sensors' mission dates up to the last COMPLETE month (not from the fires,
   and never a part month), shared by the country and any area drawn inside it.
2. Suomi NPP stopped on 2 Nov 2026. For months from S-NPP's last month on, VIIRS = k x NOAA-20,
   with k = S-NPP / NOAA-20 fitted on every full month both flew (2018 on), checked leave-one-year-out.
3. "This month so far": days 1..D of the current month against the same days of every VIIRS year.
4. Held-out R2 of the MODIS -> VIIRS factors (same leave-one-year-out as harmonize.validate).

    from syntra.pipeline import load_country
    from syntra import series
    d = load_country("Sudan")
    s = series.country_series(d["veg"], d["info"])
"""
import numpy as np
import pandas as pd

from syntra import harmonize as hz
from syntra.clean import SENSOR_START

SNPP, N20 = "N", "N20"
# First full month of each sensor, shared with syntra.clean / syntra.harmonize (S-NPP data starts 20 Jan 2012,
# so VIIRS counts from Feb 2012 and Jan 2012 is MODIS x factor).
MODIS_START, VIIRS_START = (pd.Period(year=y, month=m, freq="M") for y, m in
                            (SENSOR_START["MODIS"], SENSOR_START["VIIRS"]))


def last_full_month(day):
    """Last complete month on or before `day` (a Timestamp)."""
    return (day + pd.Timedelta(days=1)).to_period("M") - 1


def spans(last_month):
    return {"MODIS": pd.period_range(MODIS_START, last_month, freq="M"),
            "VIIRS": pd.period_range(VIIRS_START, last_month, freq="M")}


def _ym(df):
    """yyyymm as int64 (clean.py stores year as int16, and year * 100 would overflow it)."""
    return df.year.astype("int64") * 100 + df.month.astype("int64")


def _snpp_and_modis(veg):
    """Rows harmonize.py should see: MODIS and ONE VIIRS satellite (S-NPP)."""
    return veg[(veg.family == "MODIS") | (veg.satellite == SNPP)]


def _cells_per_month(rows):
    """Same count as syntra.harmonize (cell-days or cells, per hz.COUNT)."""
    return hz._count(rows)


def _cells_per_year(rows):
    """Per year, with the same count as syntra.harmonize (used for one part month at a time)."""
    if hz.COUNT == "cell_days":
        return rows.drop_duplicates(["acq_date", "cell_id"]).groupby("year").size()
    return rows.groupby("year")["cell_id"].nunique()


# ---------- NOAA-20 -> S-NPP ----------
def _pairs(veg, snpp_end):
    """Monthly counts for S-NPP and NOAA-20, full months both flew (May 2018 to before S-NPP's last month)."""
    v = veg[veg.family == "VIIRS"]
    t = pd.DataFrame({"snpp": _cells_per_month(v[v.satellite == SNPP]),
                      "n20": _cells_per_month(v[v.satellite == N20])}).dropna()
    ym = t.index.get_level_values(0).astype("int64") * 100 + t.index.get_level_values(1).astype("int64")
    stop = snpp_end.year * 100 + snpp_end.month if snpp_end is not None else 999999
    return t[(ym >= 201805) & (ym < stop)]


def fit_n20(veg, snpp_end, years=None):
    t = _pairs(veg, snpp_end)
    if years is not None:
        t = t[t.index.get_level_values(0).isin(years)]
    return float(t.snpp.sum() / t.n20.sum()) if len(t) and t.n20.sum() else float("nan")


def validate_n20(veg, snpp_end):
    t = _pairs(veg, snpp_end)
    years = sorted(set(t.index.get_level_values(0)))
    if len(years) < 2:
        return None
    yr = t.index.get_level_values(0)
    pred = np.concatenate([t.n20[yr == y].values * fit_n20(veg, snpp_end, [v for v in years if v != y]) for y in years])
    obs = np.concatenate([t.snpp[yr == y].values for y in years])
    return {"k": fit_n20(veg, snpp_end), "n_months": len(t), "years": years,
            "r2": float(1 - ((obs - pred) ** 2).sum() / ((obs - obs.mean()) ** 2).sum()),
            "bias_pct": float(100 * (pred.sum() / obs.sum() - 1))}


def _apply_n20(tab, veg, info):
    """From S-NPP's last month on, VIIRS = k x NOAA-20 (S-NPP has only part of that month)."""
    end, k = info.get("snpp_end"), info.get("k_n20")
    tab["source"] = tab.get("source", pd.Series("VIIRS observed", index=tab.index))
    if end is None or k is None or not np.isfinite(k):
        return tab
    n20 = _cells_per_month(veg[veg.satellite == N20])
    after = tab.viirs_flying & (tab.ym >= end.year * 100 + end.month)
    if after.any():
        vals = [n20.get((y, m), 0) * k for y, m in zip(tab.year[after], tab.month[after])]
        tab.loc[after, "viirs_cells"] = vals
        tab.loc[after, "harmonized_cells"] = vals
        tab.loc[after, "source"] = f"VIIRS NOAA-20 x {k:.3f} (S-NPP stopped)"
    return tab


# ---------- series ----------
def country_series(veg, info):
    """Country-wide harmonized table plus the fitted factors and validation."""
    last = last_full_month(info["complete_day"])
    sp = spans(last)
    rows = _snpp_and_modis(veg)
    rows = rows[_ym(rows) <= last.year * 100 + last.month]
    tab = hz.monthly_cells(rows, sp)
    tab, k_terra, k_terra_all = hz.modis_consistent(tab)
    tab, k_viirs, k_viirs_all = hz.harmonize(tab)
    tab = _apply_n20(tab, veg, info)
    return {"tab": tab, "k_terra": k_terra, "k_viirs": k_viirs, "k_terra_all": k_terra_all,
            "k_viirs_all": k_viirs_all, "spans": sp, "validation": hz.validate(tab), "heldout": heldout(tab)}


def area_series(veg_area, info, country):
    """Harmonized table for a drawn area, with the country's factors and month spans."""
    last = last_full_month(info["complete_day"])
    rows = _snpp_and_modis(veg_area)
    rows = rows[_ym(rows) <= last.year * 100 + last.month]
    if rows.empty:
        return None
    tab = hz.harmonize_area(rows, country["k_terra"], country["k_viirs"], country["spans"])
    tab["source"] = np.select([tab.viirs_flying, tab.ym < hz.AQUA_START],
                              ["VIIRS observed", "MODIS Terra-only, scaled"], "MODIS, scaled")
    return _apply_n20(tab, veg_area, info)


def as_series(tab, col="harmonized_cells"):
    """Monthly column as a Series with a PeriodIndex (for syntra.fire_calendar)."""
    idx = pd.PeriodIndex([pd.Period(year=int(y), month=int(m), freq="M") for y, m in zip(tab.year, tab.month)])
    return pd.Series(tab[col].values.astype(float), index=idx)


def heldout(tab, overlap=hz.OVERLAP):
    """Leave-one-year-out predictions of VIIRS from MODIS on the overlap, and their R2."""
    parts = []
    for y in range(overlap[0], overlap[1] + 1):
        k, _ = hz.monthly_factor(tab[tab.year != y], "viirs_cells", "modis_consistent", overlap)
        te = tab[(tab.year == y) & tab.viirs_flying & tab.modis_flying]
        parts.append(te.assign(pred=te.modis_consistent * te.month.map(k)))
    p = pd.concat(parts)
    o, q = p.viirs_cells.values.astype(float), p.pred.values
    r2 = 1 - ((o - q) ** 2).sum() / ((o - o.mean()) ** 2).sum()
    raw = 1 - ((o - p.modis_consistent.values) ** 2).sum() / ((o - o.mean()) ** 2).sum()
    return {"predictions": p, "r2": float(r2), "r2_raw_modis": float(raw), "n_months": len(p)}


# ---------- this month so far ----------
def month_to_date(veg, info):
    """Days 1..D of the current month vs the same days in every VIIRS year (same count as harmonize, S-NPP units).

    Uses VIIRS years only (2012 on), so no monthly factor is applied to a part month.
    Returns None when the last complete day is the end of a month.
    """
    day = info["complete_day"]
    if day.to_period("M") == last_full_month(day):
        return None
    v = veg[(veg.family == "VIIRS") & (veg.month == day.month) & (pd.to_datetime(veg.acq_date).dt.day <= day.day)]
    snpp = _cells_per_year(v[v.satellite == SNPP])
    first = VIIRS_START.year + (1 if day.month < VIIRS_START.month else 0)   # S-NPP has no early Jan 2012
    vals = {y: float(snpp.get(y, 0)) for y in range(first, day.year)}
    end, k = info.get("snpp_end"), info.get("k_n20")
    if end is not None and day > end and k is not None and np.isfinite(k):
        cur = float(_cells_per_year(v[(v.satellite == N20) & (v.year == day.year)]).sum()) * k
        src = f"NOAA-20 x {k:.3f}"
    else:
        cur, src = float(snpp.get(day.year, 0)), "S-NPP"
    hist = pd.Series(vals)
    return {"value": cur, "median": float(hist.median()), "through_day": day.day, "source": src,
            "anomaly_pct": 100 * (cur - hist.median()) / hist.median() if hist.median() > 0 else float("nan"),
            "rank": int((hist > cur).sum()) + 1, "n_years": len(hist), "p90": float(hist.quantile(0.9)),
            "by_year": pd.concat([hist, pd.Series({day.year: cur})])}
