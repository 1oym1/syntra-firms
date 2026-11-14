"""MODIS -> VIIRS harmonization (phase 4) and its validation (phase 5).

Works on the table from syntra.data.load_fires (type 0 already kept).

Method (one slide):
  1. Clean    keep confidence nominal/high for both sensors (MODIS >= 30 == VIIRS n/h).
  2. Grid     snap each hotspot to a 0.01 deg (~1 km) cell and count UNIQUE fire-cells per day.
              One fire lights several 375 m VIIRS pixels but only one ~1 km cell, which removes
              most of the resolution gap before any statistics.
  3. Fit      on the overlap 2012-2025 (MODIS and VIIRS S-NPP both flying), least squares:
                  VIIRS = a(month) + b * MODIS
              one shared slope, one intercept per calendar month (small fires only VIIRS sees).
  4. Merge    before 2012 use model(MODIS) = "VIIRS-equivalent", from 2012 use observed VIIRS.
  5. Validate leave-one-year-out: refit without year Y, predict Y from MODIS, compare with real
              VIIRS. Reported next to raw MODIS and a simple seasonal ratio (the baselines).
  6. 2026     Suomi NPP stopped on 2 Nov 2026. After its last day we use VIIRS NOAA-20 (same instrument,
              other satellite) times one ratio k = S-NPP / NOAA-20 fitted on every month both flew
              (2018-2026), also checked leave-one-year-out.

    from syntra.data import load_fires
    from syntra import harmonize as hz
    cells = hz.fire_cells(load_fires("Iraq"))
    mon   = hz.monthly(cells)
    h     = hz.harmonize(mon)          # columns modis, viirs, modis_scaled, harmonized, source
    v     = hz.validate(mon)           # v["harmonized"]["r2"], ...
"""
import numpy as np
import pandas as pd

GRID = 0.01                       # degrees, about 1.1 km
REFERENCE = "VIIRS_SNPP"          # longest VIIRS record (2012-2026); the unit we harmonize to
NOAA20 = "VIIRS_NOAA20"           # stands in for S-NPP after S-NPP's last day (2 Nov 2026)
VIIRS_START = pd.Period("2012-01", "M")
SHRINK = 50.0                     # ratio baseline: pseudo-count toward the global ratio


# ---------- 1-2. clean + grid ----------
SATELLITE_SENSOR = {"Terra": "MODIS", "Aqua": "MODIS", "T": "MODIS", "A": "MODIS",
                    "N": REFERENCE, "N20": NOAA20, "1": NOAA20}


def fire_cells(fires, sensors=("MODIS", REFERENCE)):
    """One row per (sensor, day, ~1 km cell).

    Takes syntra.clean output (confidence already filtered; rows with is_static are dropped)
    or syntra.data.load_fires output (nominal/high confidence kept here).
    """
    f = fires
    if "sensor" not in f:
        f = f.assign(sensor=f["satellite"].astype(str).map(SATELLITE_SENSOR))
    if "is_static" in f:
        f = f[~f["is_static"]]
    if "confidence_class" in f:
        f = f[f["confidence_class"].isin(["nominal", "high"])]
    f = f[f["sensor"].isin(sensors)].copy()
    f["cell_y"] = np.floor(f["latitude"] / GRID).astype("int32")
    f["cell_x"] = np.floor(f["longitude"] / GRID).astype("int32")
    f["date"] = pd.to_datetime(f["acq_date"]).dt.normalize()
    if "satellite" not in f:
        f["satellite"] = ""
    f["satellite"] = f["satellite"].astype(str)
    # A cell seen by Terra and Aqua the same day counts once; remember if Terra saw it (Terra-only fix below).
    terra = f[f["satellite"].isin(["Terra", "T"])][["sensor", "date", "cell_y", "cell_x"]].drop_duplicates()
    f = f.drop_duplicates(["sensor", "date", "cell_y", "cell_x"])
    f = f.merge(terra.assign(seen_by_terra=True), on=["sensor", "date", "cell_y", "cell_x"], how="left")
    f["seen_by_terra"] = f["seen_by_terra"].fillna(False).astype(bool)
    return f[["sensor", "satellite", "date", "latitude", "longitude", "frp", "daynight",
              "cell_y", "cell_x", "seen_by_terra"]].reset_index(drop=True)


# ---------- MODIS Terra-only months (Nov 2000 - Jun 2002), from Riyadh's notebook Part 4 ----------
AQUA_START = pd.Period("2002-07", "M")
TERRA_CAL_YEARS = range(2003, 2022)   # both satellites flying, before Terra's orbit drift
MIN_TERRA = 50                         # fewer Terra cells than this in a calendar month -> annual factor


def _terra_table(cells):
    m = cells[cells["sensor"] == "MODIS"].assign(month=lambda d: d["date"].dt.to_period("M"))
    return m.groupby("month").agg(both=("seen_by_terra", "size"), terra=("seen_by_terra", "sum"))


def terra_factors(cells, years=TERRA_CAL_YEARS):
    """k(month) = (Terra + Aqua) / Terra fire-cells, fitted on years when both flew."""
    t = _terra_table(cells)
    t = t[t.index.year.isin(list(years))]
    s = t.groupby(t.index.month)[["both", "terra"]].sum().reindex(range(1, 13), fill_value=0)
    k_all = s["both"].sum() / s["terra"].sum() if s["terra"].sum() > 0 else 1.0
    k = (s["both"] / s["terra"].replace(0, np.nan)).where(s["terra"] >= MIN_TERRA, k_all).fillna(k_all)
    return k


def validate_terra(cells, years=TERRA_CAL_YEARS):
    """Leave-one-year-out: predict Terra+Aqua from Terra alone."""
    t = _terra_table(cells)
    t = t[t.index.year.isin(list(years))]
    ys = sorted(set(t.index.year))
    if len(ys) < 2:
        return None
    pred = pd.concat([t.loc[t.index.year == y, "terra"] * t.index[t.index.year == y].month.map(
        terra_factors(cells, [v for v in ys if v != y])).values for y in ys])
    return {"years": ys, "metrics": _metrics(t.loc[pred.index, "both"].values, pred.values),
            "k": terra_factors(cells, years)}


def in_bbox(cells, bbox):
    """bbox = (west, south, east, north) or None for everything."""
    if bbox is None:
        return cells
    w, s, e, n = bbox
    return cells[cells["longitude"].between(w, e) & cells["latitude"].between(s, n)]


def monthly(cells, last_month=None, snpp_end=None, k_noaa20=None, terra_k=None):
    """Monthly fire-cell counts: columns `modis`, `viirs` (NaN before VIIRS existed), `viirs_from_noaa20`.

    With snpp_end and k_noaa20 set, days after snpp_end get k_noaa20 x NOAA-20 in the `viirs` column
    (S-NPP-equivalent); `viirs_from_noaa20` holds that part so those months can be kept out of the fit.
    With terra_k (from terra_factors) the Terra-only months before Aqua (to Jun 2002) are scaled to
    Terra + Aqua, so the MODIS record has the same meaning from start to end.
    """
    m = cells.assign(month=cells["date"].dt.to_period("M"))
    snpp = m[m["sensor"] != NOAA20] if snpp_end is None else m[(m["sensor"] != NOAA20) & (m["date"] <= snpp_end)
                                                                 | (m["sensor"] == "MODIS")]
    tab = snpp.groupby(["month", "sensor"]).size().unstack("sensor")
    tab = tab.rename(columns={"MODIS": "modis", REFERENCE: "viirs"})
    for c in ("modis", "viirs"):
        if c not in tab:
            tab[c] = np.nan
    last = last_month or (m["month"].max() if len(m) else VIIRS_START)
    idx = pd.period_range("2000-11", last, freq="M")  # MODIS archive starts Nov 2000
    tab = tab.reindex(idx).fillna(0.0)
    if terra_k is not None:
        early = tab.index < AQUA_START
        tab.loc[early, "modis"] = tab.loc[early, "modis"] * tab.index[early].month.map(terra_k).values
    tab["viirs_from_noaa20"] = 0.0
    if snpp_end is not None and k_noaa20 is not None:
        n20 = m[(m["sensor"] == NOAA20) & (m["date"] > snpp_end)].groupby("month").size() * k_noaa20
        n20 = n20.reindex(idx).fillna(0.0)
        tab["viirs"] += n20
        tab["viirs_from_noaa20"] = n20
    tab.loc[tab.index < VIIRS_START, "viirs"] = np.nan
    tab.index.name = "month"
    return tab[["modis", "viirs", "viirs_from_noaa20"]]


# ---------- 3. fit ----------
def _overlap(mon, years=None):
    ov = mon.dropna(subset=["viirs"])
    if "viirs_from_noaa20" in ov:
        ov = ov[ov["viirs_from_noaa20"] == 0]  # fit MODIS -> VIIRS on observed S-NPP only
    return ov if years is None else ov[ov.index.year.isin(years)]


def _design(idx, modis):
    return np.c_[modis, np.eye(12)[idx.month - 1]]  # [MODIS, 12 month intercepts]


def fit_model(mon, years=None):
    """Coefficients [b, a_jan, ..., a_dec] for VIIRS = a(month) + b * MODIS."""
    ov = _overlap(mon, years)
    coef, *_ = np.linalg.lstsq(_design(ov.index, ov["modis"].values), ov["viirs"].values, rcond=None)
    return coef


def predict(coef, idx, modis):
    return np.clip(_design(idx, modis) @ coef, 0, None)


def fit_ratio(mon, years=None):
    """Baseline: k(month) = VIIRS / MODIS, shrunk toward the global ratio."""
    ov = _overlap(mon, years)
    k_all = ov["viirs"].sum() / ov["modis"].sum() if ov["modis"].sum() > 0 else 1.0
    g = ov.groupby(ov.index.month)[["modis", "viirs"]].sum().reindex(range(1, 13), fill_value=0)
    return (g["viirs"] + SHRINK * k_all) / (g["modis"] + SHRINK)


# ---------- 4. merge ----------
def harmonize(mon, coef=None):
    coef = fit_model(mon) if coef is None else coef
    out = mon.copy()
    out["modis_scaled"] = predict(coef, out.index, out["modis"].values)
    out["harmonized"] = np.where(out["viirs"].isna(), out["modis_scaled"], out["viirs"])
    out["source"] = np.where(out["viirs"].isna(), "MODIS -> VIIRS-equivalent", "VIIRS S-NPP observed")
    if "viirs_from_noaa20" in out:
        out.loc[out["viirs_from_noaa20"] > 0, "source"] = "VIIRS NOAA-20 -> S-NPP-equivalent"
    return out


# ---------- 6. NOAA-20 -> S-NPP (2026) ----------
def _pair_months(cells, snpp_end=None):
    """Monthly fire-cells for S-NPP and NOAA-20, only full months where both flew."""
    v = cells[cells["sensor"].isin([REFERENCE, NOAA20])]
    if snpp_end is not None:
        v = v[v["date"] < (pd.Timestamp(snpp_end).to_period("M")).to_timestamp()]  # drop S-NPP's last partial month
    t = v.assign(month=v["date"].dt.to_period("M")).groupby(["month", "sensor"]).size().unstack("sensor")
    if REFERENCE not in t or NOAA20 not in t:
        return pd.DataFrame(columns=["snpp", "n20"])
    t = t.rename(columns={REFERENCE: "snpp", NOAA20: "n20"})[["snpp", "n20"]].dropna()
    return t[t.index >= pd.Period("2018-05", "M")]  # NOAA-20 archive starts April 2018 (partial month)


def fit_noaa20(cells, snpp_end=None, years=None):
    """k = S-NPP / NOAA-20 over the months both flew. NaN when there is no overlap."""
    t = _pair_months(cells, snpp_end)
    if years is not None:
        t = t[t.index.year.isin(years)]
    return float(t["snpp"].sum() / t["n20"].sum()) if len(t) and t["n20"].sum() > 0 else float("nan")


def validate_noaa20(cells, snpp_end=None):
    """Leave-one-year-out check of k: predict each year's S-NPP from NOAA-20."""
    t = _pair_months(cells, snpp_end)
    years = sorted(set(t.index.year))
    if len(years) < 2:
        return None
    pred = pd.concat([t.loc[t.index.year == y, "n20"] * fit_noaa20(cells, snpp_end, [v for v in years if v != y])
                      for y in years])
    obs = t.loc[pred.index, "snpp"]
    return {"years": years, "n_months": len(t), "k": fit_noaa20(cells, snpp_end),
            "raw_noaa20": _metrics(obs.values, t.loc[pred.index, "n20"].values),
            "converted": _metrics(obs.values, pred.values)}


# ---------- month to date ----------
def daily_reference(cells, coef, snpp_end=None, k_noaa20=None, terra_k=None):
    """Daily VIIRS-equivalent fire-cells over the whole record (for 'this month so far').

    Before 2012: model(MODIS) spread over the days of the month; 2012 to snpp_end: S-NPP observed;
    after snpp_end: k x NOAA-20.
    """
    d = cells.groupby(["date", "sensor"]).size().unstack("sensor")
    last = cells["date"].max()
    idx = pd.date_range("2000-11-01", last, freq="D")
    d = d.reindex(idx).fillna(0.0)
    get = lambda s: d[s] if s in d else pd.Series(0.0, index=idx)  # noqa: E731
    month_idx = idx.month - 1
    modis = get("MODIS")
    if terra_k is not None:
        modis = modis * np.where(idx < AQUA_START.to_timestamp(), terra_k.reindex(idx.month).values, 1.0)
    modis_eq = coef[0] * modis + coef[1:][month_idx] / idx.days_in_month
    ref = get(REFERENCE).copy()
    out = pd.Series(np.where(idx < VIIRS_START.to_timestamp(), np.clip(modis_eq, 0, None), ref), index=idx)
    if snpp_end is not None and k_noaa20 is not None and np.isfinite(k_noaa20):
        after = idx > pd.Timestamp(snpp_end)
        out[after] = k_noaa20 * get(NOAA20)[after]
    return out


# ---------- 5. validate ----------
def _metrics(obs, pred):
    ss_res = float(((obs - pred) ** 2).sum())
    ss_tot = float(((obs - obs.mean()) ** 2).sum())
    return {
        "r2": 1 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
        "mae": float(np.abs(obs - pred).mean()),
        "bias_pct": float(100 * (pred.sum() / obs.sum() - 1)) if obs.sum() > 0 else float("nan"),
        "r": float(np.corrcoef(obs, pred)[0, 1]) if obs.std() > 0 and pred.std() > 0 else float("nan"),
    }


def validate(mon):
    """Leave-one-year-out over the overlap years."""
    ov = mon.dropna(subset=["viirs"])
    years = sorted(set(ov.index.year))
    parts = []
    for y in years:
        train = [v for v in years if v != y]
        part = ov[ov.index.year == y]
        parts.append(part.assign(
            ratio=part["modis"] * part.index.month.map(fit_ratio(mon, train)).values,
            pred=predict(fit_model(mon, train), part.index, part["modis"].values),
        ))
    p = pd.concat(parts)
    obs = p["viirs"].values
    return {
        "years": years,
        "n_months": len(p),
        "raw_modis": _metrics(obs, p["modis"].values),
        "ratio": _metrics(obs, p["ratio"].values),
        "harmonized": _metrics(obs, p["pred"].values),
        "predictions": p,
    }
