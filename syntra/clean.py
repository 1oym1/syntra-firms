"""Step 3: clean NASA FIRMS hotspot files.

Reads the yearly CSVs in data/raw/, cleans them one file at a time (so Colab never
holds every year in memory), and writes the results to data/processed/.

    from syntra.clean import run
    fires, veg, monthly, mask = run("Sudan")

or from the repo root:

    python -m syntra.clean                 # uses DEFAULT_COUNTRY
    python -m syntra.clean --country Sudan

What it does (details in docs/FIRE_SOURCE.md):
1. Reads only the columns we need, with small dtypes, and keeps ONLY hotspots
   inside the country's border (Natural Earth 1:10m). The FIRMS country files
   already match the border, but FIRMS API data is a rectangle that includes
   neighbours (South Sudan, Chad, ...), so the clip guarantees one country.
   Use the 1:10m border: the coarse 1:50m one misplaces points near borders.
2. FLAGS static sources (type 1 volcano, 2 static land source such as gas flares,
   3 offshore) in an `is_static` column. They are kept for the map toggle and the
   static-source analysis, but every harmonization and calendar step uses
   vegetation fires only (`is_static == False`).
3. Unifies confidence: MODIS >= 30 is treated as equal to VIIRS nominal/high.
4. Drops rows with missing location/date and exact duplicates.
5. Adds year, month, a 0.1 degree grid cell id and the sensor family.
6. Builds a ~1 km static-source mask for 2026 NRT data, which has no `type` field.
7. Builds a monthly table per sensor: hotspots, burned grid cells, FRP sum.

Outputs in data/processed/:
    clean_v<N>_<inst>_<year>_<country>.parquet   one per raw file (N = CLEAN_VERSION)
    clean_vegetation_<country>.csv          all years, vegetation fires only
    static_mask_<country>.csv               ~1 km cells to drop from NRT data
    monthly_<country>.csv                   input for harmonization (Step 4)
"""
import argparse
import pathlib

import numpy as np
import pandas as pd
import requests

from syntra.data import DEFAULT_COUNTRY, PROCESSED_DIR, RAW_DIR, REPO_ROOT

GRID_DEG = 0.1      # harmonization grid (about 11 km)
MASK_DEG = 0.01     # static-source mask grid (about 1 km)
MODIS_CONF = 30     # MODIS >= 30  <=>  VIIRS n/h
CLEAN_VERSION = 2   # bump when the cleaning rules change, so old outputs are not reused
PERSISTENT_DAYS = 183   # a ~1 km cell with fire on more days than this in one year is a static source

COLS = ["latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence",
        "frp", "daynight", "type"]
DTYPES = {"latitude": "float32", "longitude": "float32", "acq_time": "int16", "frp": "float32",
          "satellite": "category", "daynight": "category", "type": "int8"}
DUP_KEYS = ["latitude", "longitude", "acq_date", "acq_time", "satellite"]

# Country borders: Natural Earth 1:10m (public domain), downloaded once into data/external/
BORDERS_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"
BORDERS_FILE = REPO_ROOT / "data" / "external" / "ne_10m_admin_0_countries.zip"
# FIRMS file name -> Natural Earth ISO code, where the names differ or are ambiguous
ISO3 = {"Sudan": "SDN", "South_Sudan": "SSD", "Saudi_Arabia": "SAU", "Democratic_Republic_of_the_Congo": "COD",
        "Republic_of_the_Congo": "COG", "United_States": "USA", "Lao_PDR": "LAO", "Swaziland": "SWZ"}


def country_shape(country=DEFAULT_COUNTRY, borders_file=BORDERS_FILE):
    """Border polygon of `country` (FIRMS spelling, e.g. 'Sudan', 'South_Sudan')."""
    import geopandas as gpd
    borders_file = pathlib.Path(borders_file)
    if not borders_file.exists():
        borders_file.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(BORDERS_URL, timeout=300)
        r.raise_for_status()
        borders_file.write_bytes(r.content)
    world = gpd.read_file(borders_file).to_crs(4326)
    iso = ISO3.get(country)
    if iso:
        sel = world[(world["ADM0_A3"] == iso) | (world["ISO_A3"] == iso)]
    else:
        name = country.replace("_", " ").lower()
        sel = world[world["ADMIN"].str.lower().eq(name) | world["NAME"].str.lower().eq(name)
                    | world["NAME_LONG"].str.lower().eq(name)]
    if sel.empty:
        raise ValueError(f"No border found for '{country}'. Add it to ISO3 in syntra/clean.py.")
    return sel.geometry.union_all()


def inside(df, shape):
    """True for rows whose point lies inside `shape`."""
    import shapely
    return shapely.contains_xy(shape, df["longitude"].to_numpy(), df["latitude"].to_numpy())


def raw_files(inst, country=DEFAULT_COUNTRY, raw_dir=RAW_DIR):
    """Yearly files of exactly this country, e.g. modis_2025_Sudan.csv.

    The year must be 4 digits: a plain "*" would also match modis_2025_South_Sudan.csv
    when looking for Sudan (or Equatorial_Guinea when looking for Guinea).
    """
    return sorted((raw_dir / inst).glob(f"{inst}_[0-9][0-9][0-9][0-9]_{country}.csv"))


def instruments(country=DEFAULT_COUNTRY, raw_dir=RAW_DIR):
    """MODIS plus ONE VIIRS series: Suomi NPP when this country has its files, otherwise NOAA-20.

    Never add both VIIRS satellites together: that doubles the counts from 2018.
    Checks the country's files, not just the folder, which can hold other countries.
    """
    return ["modis"] + (["viirs-snpp"] if raw_files("viirs-snpp", country, raw_dir) else ["viirs-jpss1"])


def cell_id(lat, lon, deg):
    """One integer per grid cell of size `deg` degrees."""
    row = np.floor((np.asarray(lat) + 90) / deg).astype("int64")
    col = np.floor((np.asarray(lon) + 180) / deg).astype("int64")
    return row * 100_000 + col


def clean_file(path, inst, shape):
    """Clean one yearly FIRMS CSV. `inst` is 'modis', 'viirs-snpp' or 'viirs-jpss1'.

    `shape` is the country border from country_shape(): points outside it are dropped.
    """
    df = pd.read_csv(path, usecols=COLS, dtype=DTYPES)
    return clean_frame(df, inst, shape, path.name)


def clean_frame(df, inst, shape=None, name=""):
    """Same cleaning for a table already in memory (yearly files and 2026 API data).

    2026 near-real-time rows have no `type`: they get type -1 here and `apply_static_mask` decides.
    shape=None skips the border clip.
    """
    df = df[[c for c in COLS if c in df]].copy()
    if "type" not in df:
        df["type"] = -1
    df["type"] = df["type"].fillna(-1).astype("int8")
    n0 = len(df)
    df = df.dropna(subset=["latitude", "longitude", "acq_date"])
    keep = inside(df, shape) if shape is not None else np.ones(len(df), bool)
    n_out = int((~keep).sum())
    df = df[keep]
    # Static sources are flagged, not dropped
    df["is_static"] = df["type"].isin([1, 2, 3])
    # Same confidence rule for both sensors (static points are kept for the map and the mask)
    if inst == "modis":
        ok = pd.to_numeric(df["confidence"], errors="coerce") >= MODIS_CONF
    else:
        ok = df["confidence"].isin(["n", "h"])
    df = df[ok | df["is_static"]]
    df = df.drop_duplicates(DUP_KEYS)
    df["acq_date"] = pd.to_datetime(df["acq_date"])
    df["year"] = df["acq_date"].dt.year.astype("int16")
    df["month"] = df["acq_date"].dt.month.astype("int8")
    df["cell_id"] = cell_id(df["latitude"], df["longitude"], GRID_DEG)
    df["family"] = "MODIS" if inst == "modis" else "VIIRS"
    df["satellite"] = df["satellite"].astype(str)
    df = df.drop(columns=["confidence"])
    if name:
        print(f"{name:36} {n0:>9,} -> {len(df):>9,} rows | outside border {n_out:,} "
              f"| static {int(df.is_static.sum()):,}")
    return df.reset_index(drop=True)


def clean_all(country=DEFAULT_COUNTRY, raw_dir=RAW_DIR, out_dir=PROCESSED_DIR, overwrite=False,
              shape=None, insts=None):
    """Clean every raw file for `country`. Returns all clean rows (static ones flagged).

    insts: optional list such as ["modis", "viirs-snpp", "viirs-jpss1"]. The app loads NOAA-20 too, only to
    calibrate it against S-NPP for 2026; the two VIIRS satellites are never added together.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    shape = country_shape(country) if shape is None else shape
    paths = []
    for inst in (insts or instruments(country, raw_dir)):
        for path in raw_files(inst, country, raw_dir):
            out = out_dir / f"clean_v{CLEAN_VERSION}_{path.stem}.parquet"
            if overwrite or not out.exists():
                clean_file(path, inst, shape).to_parquet(out, index=False)
            paths.append(out)
    if not paths:
        raise FileNotFoundError(f"No raw files for {country} in {raw_dir}. "
                                "Run: python scripts/fetch_firms.py")
    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)


def static_mask(fires):
    """~1 km cells that hold a static source: flagged in the archive, or burning on most days."""
    st = fires[fires.is_static]
    cells = set(np.unique(cell_id(st.latitude, st.longitude, MASK_DEG)).tolist())
    veg = fires[~fires.is_static]
    days = (veg.assign(mask_cell=cell_id(veg.latitude, veg.longitude, MASK_DEG))
               .groupby(["mask_cell", "year"])["acq_date"].nunique())
    persistent = set(days[days > PERSISTENT_DAYS].index.get_level_values("mask_cell").tolist())
    print(f"Static mask: {len(cells | persistent):,} cells of ~1 km "
          f"({len(persistent - cells)} found only by persistence)")
    return pd.DataFrame({"mask_cell": sorted(cells | persistent)})


def apply_static_mask(df, mask):
    """Flag hotspots that fall in a static-source cell (keeps flags that are already set).

    Use it on 2026 NRT data (no `type` field) AND on the archive, so both are cleaned the same way.
    Tested by building the mask from 2000-2024 and applying it to 2025: in Saudi Arabia 26% of type-0
    hotspots fall in static cells (flares FIRMS did not label), in Sudan 0.16%.
    """
    df = df.copy()
    in_mask = np.isin(cell_id(df.latitude, df.longitude, MASK_DEG), mask.mask_cell.values)
    df["is_static"] = (df["is_static"] if "is_static" in df else False) | in_mask
    return df


def monthly_table(veg):
    """Per sensor and month: hotspots, burned 0.1 degree cells, FRP sum.

    A month with no fires gets a row of zeros (between the sensor's first and last
    month). Without it, quiet months such as Sudan's rainy season or most months in
    Saudi Arabia would simply be missing, and a monthly median would skip them.
    """
    tab = (veg.groupby(["family", "year", "month"], observed=True)
              .agg(hotspots=("frp", "size"), burned_cells=("cell_id", "nunique"),
                   frp_sum=("frp", "sum"))
              .reset_index())
    full = []
    for fam, g in tab.groupby("family"):
        first, last = (pd.Period(year=int(y), month=int(m), freq="M")
                       for y, m in (g.iloc[0][["year", "month"]], g.iloc[-1][["year", "month"]]))
        months = pd.period_range(first, last, freq="M")
        idx = pd.MultiIndex.from_arrays([[fam] * len(months), months.year, months.month],
                                        names=["family", "year", "month"])
        full.append(g.set_index(["family", "year", "month"]).reindex(idx, fill_value=0))
    return pd.concat(full).reset_index()


def check(fires, veg, monthly):
    """Print a short quality report."""
    report = {
        "rows (clean)": len(fires),
        "vegetation rows": len(veg),
        "static rows (flagged)": int(fires.is_static.sum()),
        "duplicates left": int(fires.duplicated(DUP_KEYS).sum()),
        "missing lat/lon/date": int(fires[["latitude", "longitude", "acq_date"]].isna().any(axis=1).sum()),
        "lat range": (round(float(fires.latitude.min()), 2), round(float(fires.latitude.max()), 2)),
        "lon range": (round(float(fires.longitude.min()), 2), round(float(fires.longitude.max()), 2)),
        "years": sorted(fires.year.unique().tolist()),
        "satellites": fires.satellite.value_counts().to_dict(),
        "day / night": veg.daynight.value_counts().to_dict(),
    }
    for k, v in report.items():
        print(f"{k:24} {v}")
    print("\nMonthly vegetation fires (burned 0.1° cells):")
    print(monthly.pivot_table(index="month", columns=["family", "year"], values="burned_cells")
                 .fillna(0).astype(int))
    return report


def run(country=DEFAULT_COUNTRY, raw_dir=RAW_DIR, out_dir=PROCESSED_DIR, overwrite=False, shape=None):
    """Full Step 3. Returns (fires, veg, monthly, mask) and writes the outputs."""
    fires = clean_all(country, raw_dir, out_dir, overwrite, shape)
    veg = fires[~fires.is_static].reset_index(drop=True)
    mask = static_mask(fires)
    monthly = monthly_table(veg)
    mask.to_csv(out_dir / f"static_mask_{country}.csv", index=False)
    monthly.to_csv(out_dir / f"monthly_{country}.csv", index=False)
    veg.to_csv(out_dir / f"clean_vegetation_{country}.csv", index=False)
    print(f"\nAll clean rows: {len(fires):,} | vegetation: {len(veg):,} | "
          f"static: {int(fires.is_static.sum()):,}\n")
    check(fires, veg, monthly)
    print(f"\nSaved to {out_dir}")
    return fires, veg, monthly, mask


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Clean FIRMS hotspot files (Step 3).")
    ap.add_argument("--country", default=DEFAULT_COUNTRY, help="FIRMS country name, spaces as underscores")
    ap.add_argument("--overwrite", action="store_true", help="re-clean files already cleaned")
    a = ap.parse_args()
    run(a.country, overwrite=a.overwrite)
