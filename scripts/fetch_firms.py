"""Download NASA FIRMS yearly hotspot files for one country into data/raw.

Usage (from the repo root):
    python scripts/fetch_firms.py
    python scripts/fetch_firms.py --country Saudi_Arabia --start 2000 --end 2025

Files already on disk are skipped. No API key is needed for these yearly files.
Source: https://firms.modaps.eosdis.nasa.gov/data/country/
"""
import argparse
import pathlib

import requests

BASE = "https://firms.modaps.eosdis.nasa.gov/data/country"
INSTRUMENTS = ["modis", "viirs-snpp", "viirs-jpss1"]
RAW_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "raw"


def fetch(country: str, start: int, end: int) -> None:
    for inst in INSTRUMENTS:
        got = 0
        for year in range(start, end + 1):
            name = f"{inst}_{year}_{country}.csv"
            path = RAW_DIR / inst / name
            if path.exists():
                got += 1
                continue
            r = requests.get(f"{BASE}/{inst}/{year}/{name}", timeout=120)
            if r.status_code != 200:
                continue  # this sensor has no file for this year
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
            got += 1
        print(f"{inst:12} {got:2} yearly files")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="Saudi_Arabia", help="FIRMS country name, spaces as underscores")
    ap.add_argument("--start", type=int, default=2000)
    ap.add_argument("--end", type=int, default=2025)
    a = ap.parse_args()
    fetch(a.country, a.start, a.end)
