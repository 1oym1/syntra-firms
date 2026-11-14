"""Step 3 for the current year: download 2026 hotspots from the FIRMS API and clean them
exactly like the 2000-2025 archive.

The yearly country files stop at 2025, so this year comes from the FIRMS area API
(needs a free MAP_KEY in .env as FIRMS_MAP_KEY=..., never committed).

    python -m syntra.nrt                  # DEFAULT_COUNTRY, year 2026
    python -m syntra.nrt --country Sudan --year 2026

    from syntra.nrt import run
    fires, veg = run("Sudan")

What it does:
1. Asks FIRMS which dates each source covers. For every sensor it uses the
   standard-processing (SP) data where it exists and near-real-time (NRT) after
   that, so no day is counted twice.
2. Downloads the country's bounding box in 5-day pieces (the API maximum) and keeps
   each piece in data/raw/api/, so a rerun only fetches the last few days again.
3. Cleans with syntra.clean.clean_file: border clip, confidence rule, duplicates.
   Same code as the archive, so 2026 and 2000-2025 follow one rule.
4. Static sources: SP rows carry `type`, NRT rows do not. Every 2026 row is
   flagged static if `type` says so OR it falls in the archive's static mask
   (data/processed/static_mask_<country>.csv from `python -m syntra.clean`).
5. VIIRS: Suomi NPP stopped on 2 Nov 2026. The vegetation table uses S-NPP up to its
   last day and NOAA-20 after it (column `satellite` says which). Never both on one
   day, or the counts double. The full table keeps all three sensors for checks.

Outputs in data/processed/:
    clean_nrt_<year>_<country>.parquet       all 2026 rows, all sensors, static flagged
    clean_vegetation_nrt_<year>_<country>.csv vegetation fires, MODIS + one VIIRS per day
"""
import argparse
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

from syntra.clean import (CLEAN_VERSION, COLS, apply_static_mask, clean_file, country_shape,
                          static_mask)
from syntra.data import DEFAULT_COUNTRY, PROCESSED_DIR, RAW_DIR, REPO_ROOT

API = "https://firms.modaps.eosdis.nasa.gov/api"
API_DIR = RAW_DIR / "api"
DAYS_PER_CALL = 5          # FIRMS area API maximum
REFRESH_DAYS = 7           # pieces this close to today are fetched again (NRT fills in late)
UNKNOWN_TYPE = -1          # NRT rows have no `type`; the static mask decides for them

# Our instrument name -> (standard-processing source, near-real-time source)
SOURCES = {
    "modis": ("MODIS_SP", "MODIS_NRT"),
    "viirs-snpp": ("VIIRS_SNPP_SP", "VIIRS_SNPP_NRT"),
    "viirs-jpss1": ("VIIRS_NOAA20_SP", "VIIRS_NOAA20_NRT"),
}


def map_key():
    """FIRMS MAP_KEY from the environment or the repo's .env file."""
    key = os.environ.get("FIRMS_MAP_KEY")
    env = REPO_ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("FIRMS_MAP_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise RuntimeError("No FIRMS MAP_KEY. Put FIRMS_MAP_KEY=... in .env (never commit it).")
    return key


def availability(key):
    """First and last date FIRMS has for every source, e.g. VIIRS_SNPP_NRT up to 2026-11-02."""
    r = requests.get(f"{API}/data_availability/csv/{key}/all", timeout=60)
    r.raise_for_status()
    t = pd.read_csv(io.StringIO(r.text), parse_dates=["min_date", "max_date"])
    return t.set_index("data_id")


def plan(inst, year, avail):
    """[(source, first_day, last_day)] for one instrument: SP first, then NRT, no overlap."""
    start, end = pd.Timestamp(year, 1, 1), min(pd.Timestamp(year, 12, 31), pd.Timestamp.today().normalize())
    out, covered_to = [], start - pd.Timedelta(days=1)
    for src in SOURCES[inst]:
        if src not in avail.index:
            continue
        a = max(avail.at[src, "min_date"], covered_to + pd.Timedelta(days=1), start)
        b = min(avail.at[src, "max_date"], end)
        if a <= b:
            out.append((src, a, b))
            covered_to = b
    return out


def _bbox(shape, pad=0.1):
    w, s, e, n = shape.bounds
    return f"{w - pad:.2f},{s - pad:.2f},{e + pad:.2f},{n + pad:.2f}"


def _get(url, what, tries=5):
    """GET with retries. FIRMS drops connections when busy. Errors never print the URL (it holds the key)."""
    last = ""
    for i in range(tries):
        try:
            r = requests.get(url, timeout=(30, 300))
            if r.status_code == 200 and r.text.startswith("latitude"):
                return r.text
            last = f"HTTP {r.status_code}: {r.text[:120]}"
        except requests.RequestException as e:
            last = type(e).__name__
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"FIRMS API failed for {what} after {tries} tries ({last}). Run again later.")


def _piece(key, src, bbox, day, last_day, country):
    """One 5-day API call, cached in data/raw/api/<source>/."""
    n = min(DAYS_PER_CALL, (last_day - day).days + 1)
    path = API_DIR / src / f"{src}_{country}_{day:%Y-%m-%d}_{n}d.csv"
    fresh = day + pd.Timedelta(days=n) < pd.Timestamp.today().normalize() - pd.Timedelta(days=REFRESH_DAYS)
    if not (path.exists() and fresh):
        text = _get(f"{API}/area/csv/{key}/{src}/{bbox}/{n}/{day:%Y-%m-%d}", f"{src} {day:%Y-%m-%d}")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_text(text)
        tmp.replace(path)   # a download cut off halfway never leaves a broken file behind
    return pd.read_csv(path)


def download(inst, country, year, key, avail, shape):
    """All of `year` for one instrument as one CSV in archive format. Returns its path."""
    bbox = _bbox(shape)
    jobs = []
    for src, a, b in plan(inst, year, avail):
        for day in pd.date_range(a, b, freq=f"{DAYS_PER_CALL}D"):
            jobs.append((src, day, b))
    with ThreadPoolExecutor(max_workers=3) as pool:
        parts = list(pool.map(lambda j: _piece(key, j[0], bbox, j[1], j[2], country), jobs))
    df = pd.concat([p for p in parts if len(p)], ignore_index=True) if jobs else pd.DataFrame(columns=COLS)
    if "type" not in df:
        df["type"] = UNKNOWN_TYPE
    df["type"] = df["type"].fillna(UNKNOWN_TYPE).astype("int8")
    out = API_DIR / f"{inst}_{year}_{country}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df[COLS].to_csv(out, index=False)
    sources = ", ".join(f"{s} {a:%d %b}-{b:%d %b}" for s, a, b in plan(inst, year, avail))
    print(f"{inst:12} {len(df):>8,} raw rows  ({sources})")
    return out


def one_viirs_per_day(veg, snpp_last_day):
    """MODIS + S-NPP up to its last day + NOAA-20 after it. Never two VIIRS satellites on one day."""
    is_modis = veg.family == "MODIS"
    snpp = (veg.satellite == "N") & (veg.acq_date <= snpp_last_day)
    noaa20 = (veg.satellite == "N20") & (veg.acq_date > snpp_last_day)
    return veg[is_modis | snpp | noaa20].reset_index(drop=True)


def run(country=DEFAULT_COUNTRY, year=2026, out_dir=PROCESSED_DIR):
    """Download and clean `year`. Returns (fires: all sensors, veg: vegetation, one VIIRS per day)."""
    key = map_key()
    avail = availability(key)
    shape = country_shape(country)

    mask_path = out_dir / f"static_mask_{country}.csv"
    if mask_path.exists():
        mask = pd.read_csv(mask_path)
    else:
        from syntra.clean import clean_all
        print("No static mask yet: building it from the archive (python -m syntra.clean does this too).")
        mask = static_mask(clean_all(country, out_dir=out_dir, shape=shape))
        mask.to_csv(mask_path, index=False)

    parts = []
    for inst in SOURCES:
        raw = download(inst, country, year, key, avail, shape)
        df = clean_file(raw, inst, shape)
        by_type = df["is_static"].to_numpy()
        df = apply_static_mask(df, mask)            # NRT rows: the mask is the only way to spot flares
        df["is_static"] = df["is_static"].to_numpy() | by_type
        df["type_known"] = df["type"] != UNKNOWN_TYPE
        df["sensor"] = inst
        parts.append(df)
    fires = pd.concat(parts, ignore_index=True)

    snpp_last = fires.loc[fires.satellite == "N", "acq_date"].max()
    veg = one_viirs_per_day(fires[~fires.is_static], snpp_last)

    out_dir.mkdir(parents=True, exist_ok=True)
    fires.to_parquet(out_dir / f"clean_nrt_{year}_{country}.parquet", index=False)
    veg.drop(columns=["sensor", "type_known"]).to_csv(
        out_dir / f"clean_vegetation_nrt_{year}_{country}.csv", index=False)

    print(f"\n{year} clean rows: {len(fires):,} | static flagged: {int(fires.is_static.sum()):,} "
          f"(by type {int((fires.is_static & fires.type_known & fires.type.isin([1, 2, 3])).sum()):,}, "
          f"by mask only {int((fires.is_static & ~fires.type.isin([1, 2, 3])).sum()):,})")
    for inst, g in fires.groupby("sensor"):
        print(f"  {inst:12} {g.acq_date.min():%d %b} - {g.acq_date.max():%d %b}  {len(g):>8,} rows")
    print(f"VIIRS in the vegetation table: S-NPP to {snpp_last:%d %b %Y}, NOAA-20 after "
          f"| vegetation rows {len(veg):,}")
    print(f"Saved to {out_dir} (clean version {CLEAN_VERSION})")
    return fires, veg


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Download and clean the current year from the FIRMS API.")
    ap.add_argument("--country", default=DEFAULT_COUNTRY)
    ap.add_argument("--year", type=int, default=2026)
    a = ap.parse_args()
    run(a.country, a.year)
