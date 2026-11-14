"""Where does MODIS-to-VIIRS harmonization work best? Compare the sensors per country.

For every country with both files for the year, counts type 0 (vegetation)
hotspots per day and per month for MODIS and VIIRS NOAA-20, then measures:
  ratio         total VIIRS / total MODIS (the factor a simple harmonization would use)
  r_daily       correlation of daily counts (do the two sensors rise and fall together?)
  r_monthly     correlation of monthly counts
  ratio_cv      how much the monthly ratio moves around (low = one factor fits all year)
A country where r is high and ratio_cv is low is a good test area.

Usage (from the repo root, with data/raw/modis and data/raw/viirs-jpss1 filled):
    python scripts/compare_sensors.py --year 2025 --min-modis 500

Writes outputs/tables/sensor_agreement_<year>.csv
"""
import argparse
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


def daily_counts(path):
    df = pd.read_csv(path, usecols=["acq_date", "type"])
    df = df[df["type"] == 0]
    return df.groupby("acq_date").size()


def compare(year, min_modis):
    rows = []
    for mpath in sorted((RAW / "modis").glob(f"modis_{year}_*.csv")):
        country = mpath.stem.removeprefix(f"modis_{year}_")
        vpath = RAW / "viirs-jpss1" / f"viirs-jpss1_{year}_{country}.csv"
        if not vpath.exists():
            continue
        m = daily_counts(mpath)
        if m.sum() < min_modis:
            continue
        v = daily_counts(vpath)
        days = pd.date_range(f"{year}-01-01", f"{year}-12-31").strftime("%Y-%m-%d")
        d = pd.DataFrame({"modis": m, "viirs": v}).reindex(days, fill_value=0).fillna(0)
        d.index = pd.to_datetime(d.index)
        mo = d.resample("MS").sum()
        active = mo[mo["modis"] >= 100]  # months with too few MODIS fires give noisy ratios
        monthly_ratio = active["viirs"] / active["modis"]
        rows.append({
            "country": country,
            "modis_veg": int(d["modis"].sum()),
            "viirs_veg": int(d["viirs"].sum()),
            "ratio": round(d["viirs"].sum() / d["modis"].sum(), 2),
            "r_daily": round(d["modis"].corr(d["viirs"]), 3),
            "r_monthly": round(mo["modis"].corr(mo["viirs"]), 3),
            "ratio_cv": round(monthly_ratio.std() / monthly_ratio.mean(), 3) if len(active) >= 3 else None,
            "active_months": len(active),
        })
    t = pd.DataFrame(rows)
    # simple combined score: agreement minus instability (both 0..1-ish)
    t["score"] = (t["r_daily"] - t["ratio_cv"].fillna(1)).round(3)
    return t.sort_values("score", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--min-modis", type=int, default=500, help="skip countries with fewer MODIS vegetation hotspots")
    a = ap.parse_args()
    t = compare(a.year, a.min_modis)
    out = ROOT / "outputs" / "tables" / f"sensor_agreement_{a.year}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(out, index=False)
    print(t.head(25).to_string())
    print("...\n" + t.tail(10).to_string())
    print(f"\n{len(t)} countries -> {out}")
