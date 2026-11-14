"""
Steps 3-5 in one command: MODIS / VIIRS hotspot harmonization (SYNTRA, NASA Space Apps 2026)

Run from the repo root, after `python scripts/fetch_firms.py` (and `python -m syntra.nrt` for 2026):

    python scripts/harmonize_hotspots.py
    python scripts/harmonize_hotspots.py --country Sudan

What it does, in order (the work is done by syntra/clean.py and syntra/harmonize.py,
so this script, the app and the notebooks all give the same numbers):
1. Split the data: vegetation fires on one side; static sources (volcanoes, gas flares
   and industry, offshore platforms) isolated and saved, not counted as fires.
2. Drop weak points: low-confidence fires (MODIS < 30, VIIRS "l").
   Also keeps only points inside the country's border.
3. One way of counting: put points on a 0.1 degree grid and count fire-active
   cell-days per month (each cell once per day), so one fire counts once for both sensors.
4. MODIS consistency: before Jul 2002 only Terra flew, so those months are scaled to
   Terra+Aqua (per-month factor fitted on 2003-2021). Without this, 2001 -> 2003 shows a
   false rise.
5. Conversion: a per-month factor VIIRS / MODIS fitted on the overlap (2012-2021) turns
   MODIS before 2012 into VIIRS-equivalent. A ratio, not slope + intercept: an intercept
   adds fires to months that had none (the rainy season).
6. Test: leave-one-year-out (each overlap year predicted by factors that never saw it),
   with real R2, RMSE, and R2 on anomalies (months busier or quieter than usual).

Outputs in data/processed/:
    harmonized_monthly.csv   input for Step 4 and the app: calendar, monthly median, anomalies
    static_sources.csv       every static hotspot, e.g. for a gas-flare map layer
    static_monthly.csv       static sources per sensor and month
"""
import argparse
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from syntra import clean, harmonize  # noqa: E402
from syntra.data import DEFAULT_COUNTRY, PROCESSED_DIR  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Clean, isolate static sources and harmonize MODIS/VIIRS.")
    ap.add_argument("--country", default=DEFAULT_COUNTRY)
    a = ap.parse_args()

    # Steps 1-2: clean, isolate static sources (writes static_sources_/static_monthly_<country>.csv)
    clean.run(a.country)

    # Steps 3-6: grid, MODIS consistency, conversion, validation (adds 2026 if syntra.nrt was run)
    series, factors, val = harmonize.run(country=a.country)

    # Same file names as before, so anything built on them keeps working
    out = PROCESSED_DIR
    series.to_csv(out / "harmonized_monthly.csv", index=False)
    for name in ("static_sources", "static_monthly"):
        shutil.copyfile(out / f"{name}_{a.country}.csv", out / f"{name}.csv")

    s = harmonize.scores(series)
    print(f"\nTest (leave-one-year-out, {s['months']} months): RMSE {s['rmse']:.1f} cell-days | "
          f"R2 {s['r2']:.2f} | R2 on anomalies {s['r2_anom']:.2f}")
    print(f"Wrote harmonized_monthly.csv, static_sources.csv, static_monthly.csv to {out}")
