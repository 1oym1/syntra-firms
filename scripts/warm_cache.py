"""Download and clean countries ahead of time, so the app opens them in seconds (NFR1).

Run from the repo root before a demo or after deploying:

    python scripts/warm_cache.py                       # Sudan, Ethiopia, Saudi Arabia, Iraq
    python scripts/warm_cache.py --countries Sudan Chad

A new country needs ~60 yearly FIRMS files (about 4-6 min the first time; Ethiopia took 5.5 min). After that the archive is read from
data/processed/ (cleaned parquet per file) and this year's FIRMS API data from data/processed/cache/ (kept
3 hours), so a cold app start is ~30 s and later clicks are cached.
"""
import argparse
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from syntra.pipeline import load_country  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--countries", nargs="+", default=["Sudan", "Ethiopia", "Saudi_Arabia", "Iraq"])
    for c in ap.parse_args().countries:
        t = time.time()
        d = load_country(c)
        print(f"{c:14} {len(d['veg']):>10,} vegetation fires, data to {d['info']['complete_day']:%d %b %Y} "
              f"({time.time() - t:.0f} s)")
