"""Rank countries by vegetation-fire activity in one year of MODIS data.

First screen for picking test areas: a good area has many type 0 (vegetation)
hotspots, few static sources (gas flares), and a clear fire season.

Usage (from the repo root, after the yearly country files are in data/raw/modis):
    python scripts/screen_countries.py --year 2025

Writes outputs/tables/country_screen_modis_<year>.csv
"""
import argparse
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent


def screen(year):
    rows = []
    for path in sorted((ROOT / "data" / "raw" / "modis").glob(f"modis_{year}_*.csv")):
        country = path.stem.removeprefix(f"modis_{year}_")
        df = pd.read_csv(path, usecols=["acq_date", "confidence", "type"])
        if df.empty:
            continue
        veg = df[df["type"] == 0]
        months = pd.to_datetime(veg["acq_date"]).dt.month.value_counts()
        rows.append({
            "country": country,
            "all_hotspots": len(df),
            "vegetation": len(veg),
            "vegetation_share": round(len(veg) / len(df), 3),
            "veg_conf_30plus_share": round((veg["confidence"] >= 30).mean(), 3) if len(veg) else 0,
            "months_with_fire": int((months > 0).sum()),
            # share of the year's fires in the busiest 3 months: high = clear season
            "top3_month_share": round(months.nlargest(3).sum() / len(veg), 3) if len(veg) else 0,
        })
    return pd.DataFrame(rows).sort_values("vegetation", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2025)
    a = ap.parse_args()
    table = screen(a.year)
    out = ROOT / "outputs" / "tables" / f"country_screen_modis_{a.year}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False)
    print(table.head(30).to_string())
    print(f"\n{len(table)} countries -> {out}")
