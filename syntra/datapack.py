"""Compact, ready-to-load data for the app (fast start locally and on Streamlit Cloud).

Build it after the pipeline (fetch -> clean -> nrt -> harmonize):
    python -m syntra.datapack                 # Sudan
Load it in the app:
    pack = datapack.load("Sudan")             # dict of tables + manifest, a few seconds

Files in data/app/<country>/ (built only from data/processed, so they hold the pipeline's numbers):
    celldays.parquet    one row per fire-active 0.1 degree cell, day and satellite (vegetation fires),
                        exactly the rows syntra.harmonize counts
    points.parquet      every clean hotspot with its sensor and is_static flag, for the map
                        (historical view, filtered or unfiltered)
    harmonized.csv, factors.csv, validation.csv, static_mask.csv   copies of the pipeline outputs
    manifest.json       data-through date per sensor, clean version, build time
"""
import argparse
import json
import shutil

import numpy as np
import pandas as pd

from syntra.clean import CLEAN_VERSION
from syntra.data import DEFAULT_COUNTRY, PROCESSED_DIR, REPO_ROOT

APP_DIR = REPO_ROOT / "data" / "app"
SENSOR_OF = {"Terra": "MODIS", "Aqua": "MODIS", "N": "VIIRS_SNPP", "N20": "VIIRS_NOAA20", "N21": "VIIRS_NOAA21"}
CELL_COLS = ["family", "satellite", "year", "month", "cell_id", "frp", "acq_date"]
POINT_COLS = ["latitude", "longitude", "acq_date", "acq_time", "satellite", "frp", "daynight", "is_static"]


def _vegetation(country, src):
    """The same vegetation table syntra.harmonize.run reads: archive + years after it from syntra.nrt."""
    veg = pd.read_csv(src / f"clean_vegetation_{country}.csv", usecols=CELL_COLS)
    for p in sorted(src.glob(f"clean_vegetation_nrt_[0-9][0-9][0-9][0-9]_{country}.csv")):
        new = pd.read_csv(p, usecols=CELL_COLS)
        veg = pd.concat([veg, new[new.year > veg.year.max()]], ignore_index=True)
    veg["acq_date"] = pd.to_datetime(veg.acq_date)
    return veg


def celldays(veg):
    """One row per (day, cell, satellite) with its hotspot count and FRP: ~10x smaller than the hotspots."""
    out = (veg.groupby(["acq_date", "cell_id", "family", "satellite", "year", "month"], observed=True)
              .agg(frp=("frp", "sum"), hotspots=("frp", "size")).reset_index())
    for c in ("family", "satellite"):
        out[c] = out[c].astype("category")
    out["year"], out["month"] = out.year.astype("int16"), out.month.astype("int8")
    return out


def points(country, src):
    """Every clean hotspot (static ones flagged): archive parquet files + this year from syntra.nrt."""
    parts = [pd.read_parquet(p, columns=POINT_COLS)
             for p in sorted(src.glob(f"clean_v{CLEAN_VERSION}_*_[0-9][0-9][0-9][0-9]_{country}.parquet"))]
    archive_end = max(p.acq_date.max() for p in parts) if parts else pd.Timestamp.min
    for p in sorted(src.glob(f"clean_nrt_[0-9][0-9][0-9][0-9]_{country}.parquet")):
        new = pd.read_parquet(p, columns=POINT_COLS)
        parts.append(new[pd.to_datetime(new.acq_date) > archive_end])
    pts = pd.concat(parts, ignore_index=True)
    pts["acq_date"] = pd.to_datetime(pts.acq_date)
    pts["sensor"] = pts.satellite.map(SENSOR_OF).astype("category")
    pts["satellite"] = pts.satellite.astype("category")
    pts["daynight"] = pts.daynight.astype("category")
    pts[["latitude", "longitude", "frp"]] = pts[["latitude", "longitude", "frp"]].astype("float32")
    pts["acq_time"] = pts.acq_time.astype("int16")
    return pts.sort_values(["acq_date", "acq_time"]).reset_index(drop=True)


def build(country=DEFAULT_COUNTRY, src=PROCESSED_DIR, out=None):
    out = (out or APP_DIR) / country
    out.mkdir(parents=True, exist_ok=True)
    cd = celldays(_vegetation(country, src))
    cd.to_parquet(out / "celldays.parquet", index=False)
    pts = points(country, src)
    pts.to_parquet(out / "points.parquet", index=False)
    for name in ("harmonized", "factors", "validation", "static_mask"):
        shutil.copyfile(src / f"{name}_{country}.csv", out / f"{name}.csv")
    manifest = {
        "country": country,
        "clean_version": CLEAN_VERSION,
        "built_utc": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M"),
        "data_to": f"{cd.acq_date.max():%Y-%m-%d}",
        "sensors": {s: {"from": f"{g.acq_date.min():%Y-%m-%d}", "to": f"{g.acq_date.max():%Y-%m-%d}",
                        "hotspots": int(len(g)), "static": int(g.is_static.sum())}
                    for s, g in pts.groupby("sensor", observed=True)},
        # this year's data comes from FIRMS near-real-time: provisional until FIRMS reprocesses it
        "provisional_from": f"{pd.Timestamp(year=int(cd.year.max()), month=1, day=1):%Y-%m-%d}",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    size = sum(p.stat().st_size for p in out.iterdir()) / 1e6
    print(f"Data pack for {country}: {len(cd):,} cell-day rows, {len(pts):,} hotspots, {size:.1f} MB in {out}")
    return manifest


def load(country=DEFAULT_COUNTRY, root=None):
    """Everything the app needs for one country. Build it first with `python -m syntra.datapack`."""
    d = (root or APP_DIR) / country
    if not (d / "manifest.json").exists():
        raise FileNotFoundError(f"No data pack for {country}. Run: python -m syntra.datapack --country {country}")
    series = pd.read_csv(d / "harmonized.csv")
    return {
        "country": country,
        "manifest": json.loads((d / "manifest.json").read_text()),
        "series": series,
        "factors": exact_factors(series, pd.read_csv(d / "factors.csv").set_index("month")),
        "validation": pd.read_csv(d / "validation.csv"),
        "static_mask": pd.read_csv(d / "static_mask.csv"),
        "celldays": pd.read_parquet(d / "celldays.parquet"),
        "points": pd.read_parquet(d / "points.parquet"),
    }


def exact_factors(series, rounded):
    """The factors syntra.harmonize really used, read back from the series (factors.csv rounds to 3 decimals).

    Exact factors make daily and drawn-area numbers add up to the monthly series to the last decimal.
    """
    f = rounded.copy()
    m = series[series.modis_consistent > 0]
    f["modis_to_viirs"] = (m.modis_as_viirs / m.modis_consistent).groupby(m.month).median().reindex(f.index).fillna(f.modis_to_viirs)
    t = series[(series.terra_cells > 0) & (series.aqua_cells == 0) & series.modis_flying]
    f["terra_to_terra_aqua"] = (t.modis_consistent / t.terra_cells).groupby(t.month).median().reindex(f.index).fillna(f.terra_to_terra_aqua)
    return f


def cell_centre(cell_id, deg=0.1):
    """Centre (lat, lon) of a grid cell id from syntra.clean.cell_id."""
    row, col = np.divmod(np.asarray(cell_id), 100_000)
    return row * deg - 90 + deg / 2, col * deg - 180 + deg / 2


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build the app's compact data pack from data/processed.")
    ap.add_argument("--country", default=DEFAULT_COUNTRY)
    build(ap.parse_args().country)
