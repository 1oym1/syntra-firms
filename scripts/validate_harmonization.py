"""Step 5: validate the MODIS -> VIIRS harmonization (syntra.harmonize) in several countries.

For each country: clean data (syntra.pipeline), burned 0.1 degree cells per month, then
leave-one-year-out over the overlap 2012-2021: each year's VIIRS is predicted from MODIS with
monthly factors fitted on the other years.

Usage (from the repo root; downloads missing yearly files first):
    python scripts/validate_harmonization.py --countries Sudan Ethiopia Iraq Saudi_Arabia

Writes outputs/tables/harmonization_validation.csv (one row per country) and
outputs/tables/harmonization_validation_by_year.csv (one row per country and held-out year).
"""
import argparse
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from syntra import harmonize as hz  # noqa: E402
from syntra import series  # noqa: E402
from syntra.pipeline import load_country  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", nargs="+", default=["Sudan", "Ethiopia", "Iraq", "Saudi_Arabia"])
    ap.add_argument("--out", default=str(ROOT / "outputs" / "tables"))
    a = ap.parse_args()

    rows, by_year = [], []
    for c in a.countries:
        d = load_country(c, with_2026=False)  # validation uses the archive only (2012-2021)
        cs = series.country_series(d["veg"], d["info"])
        val, ho, tab = cs["validation"], cs["heldout"], cs["tab"]
        ov = tab[(tab.year >= hz.OVERLAP[0]) & (tab.year <= hz.OVERLAP[1])]
        rows.append({
            "country": c, "months": ho["n_months"],
            "modis_cells_per_year": round(ov.modis_consistent.sum() / ov.year.nunique()),
            "viirs_cells_per_year": round(ov.viirs_cells.sum() / ov.year.nunique()),
            "modis_to_viirs_annual": round(cs["k_viirs_all"], 3),
            "r2_raw_modis": round(ho["r2_raw_modis"], 3),
            "r2_harmonized": round(ho["r2"], 3),
            "median_abs_annual_error_pct": round(val["annual_error_%"].abs().median(), 1),
            "median_monthly_mape_pct": round(val["monthly_MAPE_%"].median(), 1),
            "median_monthly_r": round(val["monthly_r"].median(), 3),
        })
        by_year.append(val.assign(country=c))
        print(rows[-1])

    out = pathlib.Path(a.out)
    pd.DataFrame(rows).to_csv(out / "harmonization_validation.csv", index=False)
    pd.concat(by_year)[["country"] + list(by_year[0].columns[:-1])].to_csv(
        out / "harmonization_validation_by_year.csv", index=False)
    print(pd.DataFrame(rows).to_string(index=False))
