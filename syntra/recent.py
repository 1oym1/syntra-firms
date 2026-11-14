"""2026 hotspots from the FIRMS area API (the yearly archive stops at 2025).

Needs a free MAP_KEY: put FIRMS_MAP_KEY=... in .env at the repo root (never commit it),
or in Streamlit secrets when deployed.

    from syntra.clean import clean_all
    from syntra.recent import load_recent
    archive = clean_all("Sudan", insts=["modis", "viirs-snpp", "viirs-jpss1"])
    new, info = load_recent("Sudan", archive)     # same columns as clean_all

What it does
  1. Asks FIRMS which dates each source covers (data_availability) and downloads 2026 for
     MODIS, VIIRS S-NPP and VIIRS NOAA-20: standard data (SP) where it exists, then near-real-time (NRT).
     The API returns at most 5 days per call, so 2026 is fetched in 5-day chunks (cached in data/raw/api/).
  2. Keeps only hotspots inside the country. The API takes a bounding box, which also covers
     neighbours, so we keep points in 0.05 deg cells where the country had hotspots in 2000-2025.
  3. Cleans them with syntra.clean.clean_frame, exactly like the archive (confidence, duplicates,
     static flags). NRT rows have no `type`; the caller applies the static-source mask to everything.
"""
import datetime as dt
import io
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

from syntra.clean import clean_frame
from syntra.data import RAW_DIR, REPO_ROOT

API = "https://firms.modaps.eosdis.nasa.gov/api"
API_DIR = RAW_DIR / "api"
START = dt.date(2026, 1, 1)
CHUNK = 5                    # days per API call (API maximum)
FOOTPRINT_GRID = 0.05        # deg, country footprint from the archive
SOURCES = {"MODIS": "modis", "VIIRS_SNPP": "viirs-snpp", "VIIRS_NOAA20": "viirs-jpss1"}  # API prefix -> inst


def map_key():
    key = os.environ.get("FIRMS_MAP_KEY")
    env = REPO_ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("FIRMS_MAP_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    return key or None


def availability(key):
    """{data_id: (min_date, max_date)} from FIRMS."""
    r = requests.get(f"{API}/data_availability/csv/{key}/all", timeout=60)
    r.raise_for_status()
    t = pd.read_csv(io.StringIO(r.text))
    return {d: (pd.Timestamp(a).date(), pd.Timestamp(b).date()) for d, a, b in t.itertuples(index=False)}


def _plan(avail, prefix, start, end):
    """[(source, first_day, last_day)] for one sensor: SP first, NRT for the days after."""
    out, day = [], start
    for kind in ("SP", "NRT"):
        rng = avail.get(f"{prefix}_{kind}")
        if not rng:
            continue
        a, b = max(day, rng[0]), min(end, rng[1])
        if a <= b:
            out.append((f"{prefix}_{kind}", a, b))
            day = b + dt.timedelta(days=1)
    return out


def _get_chunk(key, source, bbox, first, days, country, today):
    path = API_DIR / source / f"{country}_{first:%Y-%m-%d}_{days}d.csv"
    last = first + dt.timedelta(days=days - 1)
    fresh = path.exists() and (last < today - dt.timedelta(days=2) or
                               dt.datetime.fromtimestamp(path.stat().st_mtime).date() == today)
    if not fresh:
        w, s, e, n = bbox
        url = f"{API}/area/csv/{key}/{source}/{w:.2f},{s:.2f},{e:.2f},{n:.2f}/{days}/{first:%Y-%m-%d}"
        for _ in range(3):
            try:
                r = requests.get(url, timeout=300)
                if r.status_code == 200 and r.text.startswith("latitude"):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(r.text)
                    break
            except requests.RequestException:
                pass
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["source"] = source
    return df


def download(country, bbox, key, start=START, end=None):
    """Raw API rows for 2026 (all three sensors), one table with a `source` column."""
    end = end or dt.date.today()
    avail = availability(key)
    jobs = []
    for prefix in SOURCES:
        for source, a, b in _plan(avail, prefix, start, end):
            d = a
            while d <= b:
                days = min(CHUNK, (b - d).days + 1)
                jobs.append((source, d, days))
                d += dt.timedelta(days=days)
    today = dt.date.today()
    with ThreadPoolExecutor(max_workers=6) as pool:
        parts = list(pool.map(lambda j: _get_chunk(key, j[0], bbox, j[1], j[2], country, today), jobs))
    parts = [p for p in parts if len(p)]
    raw = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if len(raw):
        raw = raw[pd.to_datetime(raw["acq_date"]).dt.date.between(start, end)]
    return raw, avail


def _cells(lat, lon, g):
    return np.floor(np.asarray(lat) / g).astype("int64") * 100000 + np.floor(np.asarray(lon) / g).astype("int64")


def load_recent(country, archive, key=None, start=START, end=None):
    """2026 hotspots for `country`, cleaned by syntra.clean.clean_frame (static mask NOT applied yet).

    archive: clean_all(country, ...) output, used for the bounding box and the country footprint.
    Returns (fires, info). fires is empty when no key is set.
    """
    key = key or map_key()
    info = {"key": bool(key), "snpp_last_day": None, "last_day": None, "dropped_outside": 0}
    if not key or archive.empty:
        return archive.iloc[0:0], info
    bbox = (archive["longitude"].min() - 0.05, archive["latitude"].min() - 0.05,
            archive["longitude"].max() + 0.05, archive["latitude"].max() + 0.05)
    raw, avail = download(country, bbox, key, start, end)
    info["snpp_last_day"] = max((v[1] for k, v in avail.items() if k.startswith("VIIRS_SNPP")), default=None)
    if not len(raw):
        return archive.iloc[0:0], info
    inside = np.isin(_cells(raw["latitude"], raw["longitude"], FOOTPRINT_GRID),
                     np.unique(_cells(archive["latitude"], archive["longitude"], FOOTPRINT_GRID)))
    info["dropped_outside"] = int((~inside).sum())
    raw = raw[inside]
    prefix = raw["source"].str.replace(r"_(SP|NRT)$", "", regex=True)
    parts = [clean_frame(raw[prefix == p], inst) for p, inst in SOURCES.items() if (prefix == p).any()]
    fires = pd.concat(parts, ignore_index=True)
    info["last_day"] = fires["acq_date"].max().date() if len(fires) else None
    return fires, info
