"""Step 4 (harmonization) and Step 5 (validation): one consistent fire series, 2000 to today.

Input: the clean vegetation fires from syntra.clean (static sources already removed).

    from syntra.clean import run as clean
    from syntra.harmonize import run as harmonize
    fires, veg, monthly, mask = clean("Sudan")
    series, factors, validation = harmonize(veg)

or from the repo root (after `python -m syntra.clean`):

    python -m syntra.harmonize

Method (details and reasons in docs/MODIS_vs_VIIRS.md):
1. Gridding. Count fire-active 0.1 degree cell-days per month (each cell once per
   day) instead of raw hotspots. This removes much of the 1 km vs 375 m resolution
   gap on its own. Counting each cell only once per MONTH saturates in the peak
   month: in Sudan's November most cells in the fire belt burn at least once, so a
   big and a quiet November looked the same (r = 0.11 with VIIRS hotspots, 0.74
   with cell-days). Set COUNT = "cells" for the old behaviour.
2. MODIS consistency. Nov 2000 to Jun 2002 only Terra flew; Aqua joined in Jul 2002.
   A per-month factor Terra -> Terra+Aqua, fitted on 2003-2021, scales the Terra-only
   months so MODIS has no jump in 2002. (2022 on is left out of the fit because
   Terra's orbit drifted.)
3. VIIRS-equivalent. A per-month factor VIIRS / MODIS, fitted on the overlap years,
   converts MODIS into VIIRS units. The final series uses observed VIIRS where it
   exists (2012 on) and MODIS x factor before that.
4. Validation. Leave-one-year-out: hide one overlap year, fit the factors on the
   others, predict that year's VIIRS from MODIS alone, and score the error.

Every factor is a ratio of sums ("pooled ratio"): sum of the target over all
calibration years divided by sum of the source. Months with too few fires fall
back to the annual factor, so a quiet month cannot produce a wild factor.

Outputs in data/processed/:
    harmonized_<country>.csv        year, month, every input, the harmonized value, its source
    factors_<country>.csv           the monthly factors (Terra->Terra+Aqua, MODIS->VIIRS)
    validation_<country>.csv        leave-one-year-out errors per year
"""
import argparse

import numpy as np
import pandas as pd

from syntra.clean import month_span
from syntra.data import DEFAULT_COUNTRY, PROCESSED_DIR

TERRA_CAL = (2003, 2021)       # both MODIS satellites, before Terra's orbit drift
OVERLAP = (2012, 2021)         # MODIS and VIIRS both flying, before Terra's orbit drift
AQUA_START = 200207            # first month with Aqua data (yyyymm)
TERRA_OUTAGE = 200106          # 15 Jun - 3 Jul 2001: Terra data gap, shown as missing data
MIN_CELLS = 50                 # fewer source cells than this in a month -> annual factor
COUNT = "cell_days"            # "cell_days": each cell once per day | "cells": once per month


def _count(df):
    """Fire-active cells per month: cell-days (needs acq_date) or unique cells."""
    if COUNT == "cell_days":
        if "acq_date" not in df:
            raise ValueError("cell-days need the acq_date column in the clean vegetation table.")
        return df.drop_duplicates(["acq_date", "cell_id"]).groupby(["year", "month"]).size()
    return df.groupby(["year", "month"])["cell_id"].nunique()


# ---------------------------------------------------------------- 1. gridded monthly table
def monthly_cells(veg, spans=None):
    """One row per month: fire-active 0.1 degree cells per sensor and satellite, plus hotspots and FRP.

    `veg` = clean vegetation fires (columns family, satellite, year, month, cell_id, frp, acq_date).
    The *_cells columns are cell-days when COUNT = "cell_days" (the default).
    Months with no fire inside the data's time span get zeros, not a missing row.
    spans: optional {"MODIS": PeriodIndex, "VIIRS": PeriodIndex} of the months each sensor covers.
    Pass the COUNTRY's spans for a small drawn area: its own fires would give a span that starts at
    the area's first fire and ends at its last one, so earlier and later years would go missing.
    """
    m = veg[veg.family == "MODIS"]
    v = veg[veg.family == "VIIRS"]
    parts = {
        "terra_cells": _count(m[m.satellite == "Terra"]),
        "aqua_cells": _count(m[m.satellite == "Aqua"]),
        "modis_cells": _count(m),          # a cell seen by Terra and Aqua on one day counts once
        "viirs_cells": _count(v),
        "modis_hotspots": m.groupby(["year", "month"]).size(),
        "viirs_hotspots": v.groupby(["year", "month"]).size(),
        "modis_frp": m.groupby(["year", "month"])["frp"].sum(),
        "viirs_frp": v.groupby(["year", "month"])["frp"].sum(),
    }
    tab = pd.DataFrame(parts)
    tab.index = pd.MultiIndex.from_arrays([tab.index.get_level_values(0).astype(int),
                                           tab.index.get_level_values(1).astype(int)],
                                          names=["year", "month"])
    # Every month each sensor covers (zeros for quiet months; see syntra.clean.month_span)
    spans = spans or {fam: month_span(veg, fam) for fam in ("MODIS", "VIIRS")}
    months = spans["MODIS"].union(spans["VIIRS"])
    full = pd.MultiIndex.from_arrays([months.year, months.month], names=["year", "month"])
    tab = tab.reindex(full).fillna(0).reset_index()
    tab["ym"] = tab.year * 100 + tab.month
    # Which sensors actually flew that month (zeros before launch are "no data", not "no fire")
    for fam, col in (("MODIS", "modis_flying"), ("VIIRS", "viirs_flying")):
        span = spans[fam]
        tab[col] = (tab.ym >= span[0].year * 100 + span[0].month) & (tab.ym <= span[-1].year * 100 + span[-1].month) \
            if len(span) else False
    return tab


# ---------------------------------------------------------------- shared: pooled monthly factor
def monthly_factor(tab, target, source, years):
    """Per calendar month: sum(target) / sum(source) over `years`; quiet months use the annual factor."""
    cal = tab[(tab.year >= years[0]) & (tab.year <= years[1])]
    s = cal.groupby("month")[[target, source]].sum()
    annual = cal[target].sum() / cal[source].sum() if cal[source].sum() else np.nan
    k = s[target] / s[source].replace(0, np.nan)
    k = k.where(s[source] >= MIN_CELLS, annual).fillna(annual)
    return k.reindex(range(1, 13)).fillna(annual), annual


# ---------------------------------------------------------------- 2. MODIS consistency (Terra -> Terra+Aqua)
def modis_consistent(tab, years=TERRA_CAL):
    """Adds `modis_consistent`: Terra-only months scaled to Terra+Aqua. Returns (tab, k_month, k_annual)."""
    tab = tab.copy()
    k, k_all = monthly_factor(tab, "modis_cells", "terra_cells", years)
    terra_only = tab.modis_flying & (tab.ym < AQUA_START)
    tab["modis_consistent"] = tab.modis_cells.astype(float)
    if terra_only.any():
        if np.isnan(k_all):
            raise ValueError(f"Cannot scale Terra-only months: no calibration data in {years}.")
        tab.loc[terra_only, "modis_consistent"] = tab.loc[terra_only, "terra_cells"] * tab.loc[terra_only, "month"].map(k)
    return tab, k, k_all


# ---------------------------------------------------------------- 3. VIIRS-equivalent series
def harmonize(tab, overlap=OVERLAP):
    """Adds `harmonized_cells` (VIIRS units) and `source`. Returns (tab, k_month, k_annual)."""
    tab = tab.copy()
    k, k_all = monthly_factor(tab, "viirs_cells", "modis_consistent", overlap)
    if np.isnan(k_all):
        raise ValueError(f"No MODIS/VIIRS overlap in {overlap}: download those years first.")
    tab["modis_as_viirs"] = tab.modis_consistent * tab.month.map(k)
    tab["harmonized_cells"] = np.where(tab.viirs_flying, tab.viirs_cells, tab.modis_as_viirs)
    tab["source"] = np.select(
        [tab.viirs_flying, tab.modis_flying & (tab.ym < AQUA_START), tab.modis_flying],
        ["VIIRS observed", "MODIS Terra-only, scaled", "MODIS, scaled"], default="no data")
    tab.loc[tab.source == "no data", "harmonized_cells"] = np.nan
    tab["flag"] = np.where(tab.ym == TERRA_OUTAGE, "Terra outage 15 Jun - 3 Jul 2001: undercount", "")
    return tab, k, k_all


# ---------------------------------------------------------------- 4. validation (Step 5)
def validate(tab, overlap=OVERLAP):
    """Leave-one-year-out on the overlap: predict each year's VIIRS from MODIS with factors fitted on the others."""
    rows = []
    years = range(overlap[0], overlap[1] + 1)
    for y in years:
        k, _ = monthly_factor(tab[tab.year != y], "viirs_cells", "modis_consistent", overlap)
        te = tab[(tab.year == y) & tab.viirs_flying & tab.modis_flying]
        if te.empty or te.viirs_cells.sum() == 0:
            continue
        pred = te.modis_consistent * te.month.map(k)
        busy = te.viirs_cells >= MIN_CELLS                     # % errors only where there is fire to measure
        rows.append({
            "year": y,
            "viirs_cells": int(te.viirs_cells.sum()),
            "predicted_cells": round(float(pred.sum())),
            "annual_error_%": round(float((pred.sum() - te.viirs_cells.sum()) / te.viirs_cells.sum() * 100), 1),
            "monthly_MAPE_%": round(float((abs(pred[busy] - te.viirs_cells[busy]) / te.viirs_cells[busy]).mean() * 100), 1)
                              if busy.any() else np.nan,
            "monthly_r": round(float(np.corrcoef(pred, te.viirs_cells)[0, 1]), 3) if len(te) > 2 else np.nan,
        })
    return pd.DataFrame(rows)


def scores(tab, overlap=OVERLAP):
    """One set of numbers for the slides, pooled over all leave-one-year-out predictions.

    r2       real R2 (1 - SS_res / SS_tot), not the squared correlation
    rmse     root mean square error, in cell-days per month
    r2_anom  R2 after removing each calendar month's mean: how well the model gets a
             month that is busier or quieter than usual, not just the seasonal cycle
    """
    parts = []
    for y in range(overlap[0], overlap[1] + 1):
        k, _ = monthly_factor(tab[tab.year != y], "viirs_cells", "modis_consistent", overlap)
        te = tab[(tab.year == y) & tab.viirs_flying & tab.modis_flying]
        parts.append(te.assign(pred=te.modis_consistent * te.month.map(k)))
    p = pd.concat(parts)
    obs, pred = p.viirs_cells, p.pred

    def r2(o, q):
        return float(1 - ((o - q) ** 2).sum() / ((o - o.mean()) ** 2).sum())

    anom_o = obs - p.groupby("month").viirs_cells.transform("mean")
    anom_p = pred - p.groupby("month").pred.transform("mean")
    return {"months": len(p), "r2": round(r2(obs, pred), 3),
            "rmse": round(float(np.sqrt(((obs - pred) ** 2).mean())), 1),
            "r2_anom": round(r2(anom_o, anom_p), 3)}


# ---------------------------------------------------------------- for the app: any area the user draws
def harmonize_area(veg_area, k_terra, k_viirs, spans=None):
    """Harmonized monthly series for a user-drawn area, using factors fitted on the whole country.

    Small areas have too few fires to fit their own factors, so the country's factors are reused.
    spans: the country's month spans (see monthly_cells), so every year is in the table.
    """
    tab = monthly_cells(veg_area, spans)
    terra_only = tab.modis_flying & (tab.ym < AQUA_START)
    tab["modis_consistent"] = tab.modis_cells.astype(float)
    tab.loc[terra_only, "modis_consistent"] = tab.loc[terra_only, "terra_cells"] * tab.loc[terra_only, "month"].map(k_terra)
    tab["modis_as_viirs"] = tab.modis_consistent * tab.month.map(k_viirs)
    tab["harmonized_cells"] = np.where(tab.viirs_flying, tab.viirs_cells, tab.modis_as_viirs)
    return tab


# ---------------------------------------------------------------- run everything
def run(veg=None, country=DEFAULT_COUNTRY, out_dir=PROCESSED_DIR):
    """Full Steps 4-5. Returns (series, factors, validation) and writes the outputs.

    Without `veg` it reads the cleaned archive and, if present, the current year from
    syntra.nrt, so the series runs from 2000 to the latest day FIRMS has.
    """
    last_day = None
    if veg is None:
        cols = ["family", "satellite", "year", "month", "cell_id", "frp", "acq_date"]
        veg = pd.read_csv(out_dir / f"clean_vegetation_{country}.csv", usecols=cols)
        # Current year from the FIRMS API (python -m syntra.nrt), cleaned with the same rules
        nrt = sorted(out_dir.glob(f"clean_vegetation_nrt_[0-9][0-9][0-9][0-9]_{country}.csv"))
        if nrt:
            new = pd.concat([pd.read_csv(p, usecols=cols) for p in nrt], ignore_index=True)
            new = new[new.year > veg.year.max()]          # never count a year twice
            last_day = pd.to_datetime(new.acq_date).max()
            veg = pd.concat([veg, new], ignore_index=True)
            print(f"Added {len(new):,} vegetation fires from the FIRMS API, data to {last_day:%d %b %Y}")
    tab = monthly_cells(veg)
    tab, k_terra, k_terra_all = modis_consistent(tab)
    series, k_viirs, k_viirs_all = harmonize(tab)
    if last_day is not None and last_day < last_day + pd.offsets.MonthEnd(0):
        # The newest month is not over: compare it with the same days of earlier years, not whole months
        partial = series.ym == last_day.year * 100 + last_day.month
        series.loc[partial, "flag"] = f"partial month: data to {last_day:%d %b %Y}"
    val = validate(series)

    factors = pd.DataFrame({"month": range(1, 13),
                            "terra_to_terra_aqua": k_terra.round(3).values,
                            "modis_to_viirs": k_viirs.round(3).values})
    series.to_csv(out_dir / f"harmonized_{country}.csv", index=False)
    factors.to_csv(out_dir / f"factors_{country}.csv", index=False)
    val.to_csv(out_dir / f"validation_{country}.csv", index=False)

    print(f"Terra -> Terra+Aqua (fit {TERRA_CAL[0]}-{TERRA_CAL[1]}): annual {k_terra_all:.2f}")
    print(f"MODIS -> VIIRS      (fit {OVERLAP[0]}-{OVERLAP[1]}): annual {k_viirs_all:.2f}")
    print(factors.to_string(index=False))
    if not val.empty:
        print("\nLeave-one-year-out validation:")
        print(val.to_string(index=False))
        print(f"\nMedian |annual error| {val['annual_error_%'].abs().median():.1f}% | "
              f"median monthly MAPE {val['monthly_MAPE_%'].median():.1f}% | "
              f"median monthly r {val['monthly_r'].median():.3f}")
        s = scores(series)
        print(f"Pooled over {s['months']} held-out months: R2 {s['r2']:.3f} | RMSE {s['rmse']:.1f} "
              f"cell-days | R2 on anomalies (month minus its usual level) {s['r2_anom']:.3f}")
    print(f"\nSaved to {out_dir}")
    return series, factors, val


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Harmonize MODIS and VIIRS into one series (Steps 4-5).")
    ap.add_argument("--country", default=DEFAULT_COUNTRY)
    a = ap.parse_args()
    run(country=a.country)
