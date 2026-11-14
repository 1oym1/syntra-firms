"""Download NASA FIRMS yearly hotspot files for one country into data/raw.

Usage (from the repo root):
    python scripts/fetch_firms.py
    python scripts/fetch_firms.py --country Saudi_Arabia --start 2000 --end 2025

Files already on disk are skipped. No API key is needed for these yearly files.
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from syntra.data import fetch  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="Saudi_Arabia", help="FIRMS country name, spaces as underscores")
    ap.add_argument("--start", type=int, default=2000)
    ap.add_argument("--end", type=int, default=2025)
    a = ap.parse_args()
    fetch(a.country, a.start, a.end)
