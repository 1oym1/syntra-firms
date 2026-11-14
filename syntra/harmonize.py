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
REFERENCE = "VIIRS_SNPP"          # longest VIIRS record (2012-2025); the unit we harmonize to
VIIRS_START = pd.Period("2012-01", "M")
SHRINK = 50.0                     # ratio baseline: pseudo-count toward the global ratio


# ---------- 1-2. clean + grid ----------
def fire_cells(fires, sensors=("MODIS", REFERENCE)):
    """One row per (sensor, day, ~1 km cell). Keeps nominal/high confidence only."""
    f = fires[fires["sensor"].isin(sensors) & fires["confidence_class"].isin(["nominal", "high"])].copy()
    f["cell_y"] = np.floor(f["latitude"] / GRID).astype("int32")
    f["cell_x"] = np.floor(f["longitude"] / GRID).astype("int32")
    f["date"] = f["acq_date"].dt.normalize()
    f = f.drop_duplicates(["sensor", "date", "cell_y", "cell_x"])
    return f[["sensor", "date", "latitude", "longitude", "frp", "daynight", "cell_y", "cell_x"]].reset_index(drop=True)


def in_bbox(cells, bbox):
    """bbox = (west, south, east, north) or None for everything."""
    if bbox is None:
        return cells
    w, s, e, n = bbox
    return cells[cells["longitude"].between(w, e) & cells["latitude"].between(s, n)]


def monthly(cells, last_month=None):
    """Monthly fire-cell counts: columns `modis`, `viirs` (NaN before VIIRS existed)."""
    m = cells.assign(month=cells["date"].dt.to_period("M"))
    tab = m.groupby(["month", "sensor"]).size().unstack("sensor")
    tab = tab.rename(columns={"MODIS": "modis", REFERENCE: "viirs"})
    for c in ("modis", "viirs"):
        if c not in tab:
            tab[c] = np.nan
    last = last_month or (tab.index.max() if len(tab) else VIIRS_START)
    idx = pd.period_range("2000-11", last, freq="M")  # MODIS archive starts Nov 2000
    tab = tab.reindex(idx).fillna(0.0)
    tab.loc[tab.index < VIIRS_START, "viirs"] = np.nan
    tab.index.name = "month"
    return tab[["modis", "viirs"]]


# ---------- 3. fit ----------
def _overlap(mon, years=None):
    ov = mon.dropna(subset=["viirs"])
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
    out["source"] = np.where(out["viirs"].isna(), "MODIS -> VIIRS-equivalent", "VIIRS observed")
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
