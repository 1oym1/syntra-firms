"""Step 3 of the team checklist: how MODIS and VIIRS differ (resolution and sensitivity), on clean data.

Input: clean vegetation fires from syntra.pipeline.load_country (static sources removed, inside the border).
Compares MODIS (Terra + Aqua) with ONE VIIRS satellite (Suomi NPP) over full years both flew.

    from syntra.pipeline import load_country
    from syntra import compare
    d = load_country("Sudan", with_2026=False)
    compare.yearly(d["veg"])          # hotspots vs burned 0.1 deg cells, per sensor, per year
    compare.by_month(d["veg"])        # the same, pooled per calendar month (seasonality of the gap)
    compare.same_pass(d["veg"])       # Aqua vs S-NPP on the same afternoon pass: who sees what
    compare.frp_summary(d["veg"])     # fire radiative power: how small are the fires each sensor sees

Questions it answers
1. Resolution: VIIRS pixels are ~7x smaller, so one fire gives several VIIRS hotspots. Counting burned
   0.1 deg cells instead of points removes much of that (hotspot ratio vs cell ratio).
2. Sensitivity: does VIIRS see the fires MODIS sees, plus extra small ones? Aqua and Suomi NPP both pass at
   about 13:30 local time, so on the same day and the same 0.1 deg cell they look at the same fire.
"""
import numpy as np
import pandas as pd

SNPP = "N"
YEARS = (2012, 2025)      # full years with MODIS and Suomi NPP (2026 is near-real-time and partial)


def _pair(veg, years=YEARS):
    """MODIS (Terra + Aqua) and VIIRS S-NPP rows in the comparison years."""
    v = veg[(veg.year >= years[0]) & (veg.year <= years[1])]
    return v[v.family == "MODIS"], v[v.satellite == SNPP]



def yearly(veg, years=YEARS):
    """Per year: hotspots and burned 0.1 deg cell-months per sensor, and the VIIRS/MODIS ratio of each."""
    m, v = _pair(veg, years)
    cm = m.groupby(["year", "month"])["cell_id"].nunique().groupby("year").sum()
    cv = v.groupby(["year", "month"])["cell_id"].nunique().groupby("year").sum()
    t = pd.DataFrame({"modis_hotspots": m.groupby("year").size(), "viirs_hotspots": v.groupby("year").size(),
                      "modis_cells": cm, "viirs_cells": cv}).fillna(0).astype(int)
    t["hotspot_ratio"] = (t.viirs_hotspots / t.modis_hotspots).round(2)
    t["cell_ratio"] = (t.viirs_cells / t.modis_cells).round(2)
    t.index = t.index.astype(int)
    return t


def by_month(veg, years=YEARS):
    """Per calendar month, pooled over the years: hotspots, cells and both ratios (seasonality of the gap)."""
    m, v = _pair(veg, years)
    cm = m.groupby(["year", "month"])["cell_id"].nunique().groupby("month").sum()
    cv = v.groupby(["year", "month"])["cell_id"].nunique().groupby("month").sum()
    t = pd.DataFrame({"modis_hotspots": m.groupby("month").size(), "viirs_hotspots": v.groupby("month").size(),
                      "modis_cells": cm, "viirs_cells": cv}).reindex(range(1, 13)).fillna(0).astype(int)
    t["hotspot_ratio"] = (t.viirs_hotspots / t.modis_hotspots.replace(0, np.nan)).round(2)
    t["cell_ratio"] = (t.viirs_cells / t.modis_cells.replace(0, np.nan)).round(2)
    t.index = t.index.astype(int)
    return t


def monthly_correlation(veg, years=YEARS):
    """Pearson r of the monthly series (hotspots and cells) between MODIS and VIIRS S-NPP."""
    m, v = _pair(veg, years)
    keys = ["year", "month"]
    hs = pd.DataFrame({"m": m.groupby(keys).size(), "v": v.groupby(keys).size()}).fillna(0)
    cs = pd.DataFrame({"m": m.groupby(keys)["cell_id"].nunique(), "v": v.groupby(keys)["cell_id"].nunique()}).fillna(0)
    return {"r_hotspots": float(np.corrcoef(hs.m, hs.v)[0, 1]), "r_cells": float(np.corrcoef(cs.m, cs.v)[0, 1]),
            "n_months": len(cs)}


def same_pass(veg, years=YEARS):
    """Aqua vs Suomi NPP, daytime, same date and same 0.1 deg cell (both pass at about 13:30).

    Returns the shares of each sensor's cell-days the other one also saw, the median FRP of
    cell-days seen by both vs by VIIRS only, and the same shares per calendar month.
    """
    v0 = veg[(veg.year >= years[0]) & (veg.year <= years[1]) & (veg.daynight == "D")]

    def cell_days(rows):
        g = rows.groupby(["acq_date", "cell_id"]).agg(frp=("frp", "max"), month=("month", "first"))
        return g

    a = cell_days(v0[v0.satellite == "Aqua"])
    n = cell_days(v0[v0.satellite == SNPP])
    both = n.index.intersection(a.index)
    n_only = n.index.difference(a.index)
    a_only = a.index.difference(n.index)
    out = {
        "aqua_cell_days": len(a), "snpp_cell_days": len(n), "both": len(both),
        "share_of_aqua_seen_by_snpp": len(both) / len(a) if len(a) else np.nan,
        "share_of_snpp_seen_by_aqua": len(both) / len(n) if len(n) else np.nan,
        "snpp_frp_median_both": float(n.loc[both, "frp"].median()),
        "snpp_frp_median_snpp_only": float(n.loc[n_only, "frp"].median()),
        "aqua_frp_median_both": float(a.loc[both, "frp"].median()),
        "aqua_frp_median_aqua_only": float(a.loc[a_only, "frp"].median()),
    }
    mon = pd.DataFrame({
        "snpp_cell_days": n.groupby("month").size(),
        "aqua_cell_days": a.groupby("month").size(),
        "both": n.loc[both].groupby("month").size(),
    }).reindex(range(1, 13)).fillna(0).astype(int)
    mon["share_of_aqua_seen_by_snpp"] = (mon.both / mon.aqua_cell_days.replace(0, np.nan)).round(3)
    mon["share_of_snpp_seen_by_aqua"] = (mon.both / mon.snpp_cell_days.replace(0, np.nan)).round(3)
    out["by_month"] = mon
    out["frp"] = {"VIIRS seen by both": n.loc[both, "frp"].values, "VIIRS only": n.loc[n_only, "frp"].values}
    return out


def frp_summary(veg, years=YEARS):
    """FRP (MW) percentiles and day/night split per sensor. Note: FRP is per pixel, and a MODIS pixel is
    ~7x larger, so compare the SHAPE (how many small fires each sees), not the raw MW."""
    m, v = _pair(veg, years)
    rows = []
    for name, d in (("MODIS (Terra+Aqua)", m), ("VIIRS S-NPP", v)):
        q = d.frp.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
        rows.append({"sensor": name, "hotspots": len(d), "frp_p10": q[0.1], "frp_p25": q[0.25],
                     "frp_median": q[0.5], "frp_p75": q[0.75], "frp_p90": q[0.9],
                     "share_below_5MW": float((d.frp < 5).mean()), "share_night": float((d.daynight == "N").mean())})
    return pd.DataFrame(rows).set_index("sensor").round(3)
