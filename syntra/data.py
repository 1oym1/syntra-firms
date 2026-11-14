"""Download and load NASA FIRMS hotspot files.

Notebooks, scripts and the app all import from here, so a fix made once
reaches everyone.

    from syntra.data import fetch, load_fires
    fetch("Sudan", 2000, 2025)
    fires = load_fires("Sudan")
"""
import pathlib
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/data/country"
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

# Area the team builds and tests on (see docs/DECISIONS.md). Change it here only.
DEFAULT_COUNTRY = "Sudan"

# FIRMS folder name -> label we use everywhere
INSTRUMENTS = {
    "modis": "MODIS",
    "viirs-snpp": "VIIRS_SNPP",
    "viirs-jpss1": "VIIRS_NOAA20",
}

COLUMNS = ["sensor", "family", "satellite", "latitude", "longitude", "acq_date",
           "acq_datetime_utc", "year", "month", "daynight", "confidence_class",
           "confidence_pct", "frp", "bright_main", "bright_second", "scan", "track",
           "type", "version"]


def fetch(country=DEFAULT_COUNTRY, start=2000, end=2025, download=True, instruments=None):
    """Get the yearly CSVs into data/raw. Returns {instrument: [paths]}.

    Files already on disk are reused. With download=False nothing is fetched.
    No API key is needed for these yearly files (they stop at 2025).
    """
    def get(inst, year):
        name = f"{inst}_{year}_{country}.csv"
        path = RAW_DIR / inst / name
        if not path.exists() and download:
            r = requests.get(f"{BASE_URL}/{inst}/{year}/{name}", timeout=300)
            if r.status_code == 200:  # otherwise this sensor has no file that year
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(r.content)
        return path if path.exists() else None

    # FIRMS is slow per file but fine with several at once: ~1 min for a country instead of ~30.
    insts = list(instruments or INSTRUMENTS)
    jobs = [(inst, year) for inst in insts for year in range(start, end + 1)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(lambda j: get(*j), jobs))
    files = {inst: [] for inst in insts}
    for (inst, _), path in zip(jobs, paths):
        if path is not None:
            files[inst].append(path)
    for inst, got in files.items():
        print(f"{inst:12} {len(got):2} yearly files")
    return files


def _load_instrument(inst, paths):
    if not paths:
        return pd.DataFrame()
    df = pd.concat((pd.read_csv(p) for p in paths), ignore_index=True)
    df = df.rename(columns={"brightness": "bright_main", "bright_t31": "bright_second",
                            "bright_ti4": "bright_main", "bright_ti5": "bright_second"})
    df["sensor"] = INSTRUMENTS[inst]
    df["family"] = "MODIS" if inst == "modis" else "VIIRS"
    if inst == "modis":
        # MODIS user guide, Table 11: <30 low, 30-79 nominal, >=80 high
        df["confidence_pct"] = pd.to_numeric(df["confidence"], errors="coerce")
        df["confidence_class"] = pd.cut(df["confidence_pct"], [-1, 29.999, 79.999, 100],
                                        labels=["low", "nominal", "high"]).astype(str)
    else:
        df["confidence_pct"] = pd.NA
        df["confidence_class"] = df["confidence"].map({"l": "low", "n": "nominal", "h": "high"})
    return df


def load_fires(country=DEFAULT_COUNTRY, start=2000, end=2025, vegetation_only=True,
               download=True, instruments=None):
    """One table for MODIS and VIIRS with the same column names.

    vegetation_only keeps type 0 (presumed vegetation fire). Type 2 = static
    sources such as gas flares, 1 = volcano, 3 = offshore.
    instruments: optional subset of INSTRUMENTS keys, e.g. ("modis", "viirs-snpp").
    """
    files = fetch(country, start, end, download=download, instruments=instruments)
    fires = pd.concat([_load_instrument(i, files[i]) for i in files], ignore_index=True)
    fires["acq_date"] = pd.to_datetime(fires["acq_date"])
    hhmm = fires["acq_time"].astype(int).astype(str).str.zfill(4)
    fires["acq_datetime_utc"] = (fires["acq_date"]
                                 + pd.to_timedelta(hhmm.str[:2].astype(int), unit="h")
                                 + pd.to_timedelta(hhmm.str[2:].astype(int), unit="m"))
    fires["year"] = fires["acq_date"].dt.year
    fires["month"] = fires["acq_date"].dt.month
    fires = fires[COLUMNS]
    if vegetation_only:
        fires = fires[fires["type"] == 0].reset_index(drop=True)
    return fires
