"""Step 3 of the team checklist: how MODIS and VIIRS differ (resolution and sensitivity), on clean data.

Input: clean vegetation fires from syntra.pipeline.load_country (static sources removed, inside the border).
Compares MODIS (BOTH satellites, Terra + Aqua) with ONE VIIRS satellite (Suomi NPP) over full years both flew.
Read the ratios that way: against Aqua alone, S-NPP has about 7x the hotspots in Sudan, against Terra alone ~11x.

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
   about 13:30 local time, so on the same day near the same 0.1 deg cell they look at the same fire
   (same_pass corrects for swath gaps and pixel size; see its docstring).
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


def _cell_days(rows):
    """One row per (day, 0.1 deg cell, 1 deg box) with the strongest FRP that day."""
    r = rows.assign(cy=np.floor(rows.latitude * 10).astype(int), cx=np.floor(rows.longitude * 10).astype(int),
                    by=np.floor(rows.latitude).astype(int), bx=np.floor(rows.longitude).astype(int))
    return r.groupby(["acq_date", "cy", "cx"], as_index=False).agg(by=("by", "first"), bx=("bx", "first"),
                                                                    month=("month", "first"), frp=("frp", "max"))


def _seen_by(src, other, neighbours=True):
    """True where `other` has fire on the same day in the same 0.1 deg cell (or a neighbouring one)."""
    keys = other[["acq_date", "cy", "cx"]].drop_duplicates()
    hit = np.zeros(len(src), bool)
    offs = [(i, j) for i in (-1, 0, 1) for j in (-1, 0, 1)] if neighbours else [(0, 0)]
    base = src[["acq_date", "cy", "cx"]].reset_index(drop=True)
    for i, j in offs:
        k = keys.assign(cy=keys.cy - i, cx=keys.cx - j, _hit=True)
        hit |= base.merge(k, on=["acq_date", "cy", "cx"], how="left")["_hit"].notna().to_numpy()
    return hit


def same_pass(veg, years=(2012, 2021), coverage=True, neighbours=True):
    """Aqua (MODIS) vs Suomi NPP (VIIRS), daytime, same date: who sees whose fires.

    Both pass at about 13:30 local time (Sudan: median 11:36 vs 11:25 UTC), so they look at the same fires.
    Two corrections make it a fair test:
    - coverage=True: only 1 deg boxes where BOTH satellites detected some fire that day. Aqua's swath is
      narrower (2,330 vs 3,060 km) and leaves gaps near the equator; a fire Aqua never flew over is not a miss.
    - neighbours=True: a fire in the next 0.1 deg cell counts as seen. MODIS pixels grow to ~2 x 4.8 km at the
      swath edge, so the same fire can land in the cell next door.
    years: 2012-2021 by default, before Aqua's orbit began to drift (same overlap as syntra.harmonize).
    """
    x = veg[(veg.year >= years[0]) & (veg.year <= years[1]) & (veg.daynight == "D")]
    a, n = _cell_days(x[x.satellite == "Aqua"]), _cell_days(x[x.satellite == SNPP])
    if coverage:
        boxes = a[["acq_date", "by", "bx"]].drop_duplicates().merge(n[["acq_date", "by", "bx"]].drop_duplicates())
        a, n = a.merge(boxes), n.merge(boxes)
    a["seen"], n["seen"] = _seen_by(a, n, neighbours), _seen_by(n, a, neighbours)
    out = {
        "years": years, "coverage": coverage, "neighbours": neighbours,
        "aqua_cell_days": len(a), "snpp_cell_days": len(n),
        "share_of_aqua_seen_by_snpp": float(a.seen.mean()), "share_of_snpp_seen_by_aqua": float(n.seen.mean()),
        "snpp_frp_median_both": float(n.loc[n.seen, "frp"].median()),
        "snpp_frp_median_snpp_only": float(n.loc[~n.seen, "frp"].median()),
    }
    mon = pd.DataFrame({"aqua_cell_days": a.groupby("month").size(), "snpp_cell_days": n.groupby("month").size(),
                        "share_of_aqua_seen_by_snpp": a.groupby("month").seen.mean(),
                        "share_of_snpp_seen_by_aqua": n.groupby("month").seen.mean()}).reindex(range(1, 13))
    out["by_month"] = mon.round(3)
    out["frp"] = {"VIIRS seen by both": n.loc[n.seen, "frp"].values, "VIIRS only": n.loc[~n.seen, "frp"].values}
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
