"""Phase 5: validate the MODIS -> VIIRS harmonization in several countries.

For each country: leave-one-year-out over 2012-2025 (MODIS + VIIRS S-NPP overlap), monthly
fire-cell counts. Compares raw MODIS, a seasonal ratio, and our seasonal linear model.

Usage (from the repo root; downloads missing yearly files first):
    python scripts/validate_harmonization.py --countries Sudan Ethiopia Iraq Saudi_Arabia

Writes outputs/tables/harmonization_validation.csv
"""
import argparse
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from syntra import harmonize as hz  # noqa: E402
from syntra.data import load_fires  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", nargs="+", default=["Sudan", "Ethiopia", "Iraq", "Saudi_Arabia"])
    a = ap.parse_args()

    rows = []
    for c in a.countries:
        fires = load_fires(c, instruments=("modis", "viirs-snpp"))
        cells = hz.fire_cells(fires)
        mon = hz.monthly(cells)
        v = hz.validate(mon)
        ov = mon.dropna(subset=["viirs"])
        row = {"country": c, "months": v["n_months"],
               "modis_cells_per_year": round(ov["modis"].sum() / len(v["years"])),
               "viirs_cells_per_year": round(ov["viirs"].sum() / len(v["years"]))}
        for k, name in [("raw_modis", "raw"), ("ratio", "ratio"), ("harmonized", "model")]:
            row[f"r2_{name}"] = round(v[k]["r2"], 3)
            row[f"bias_pct_{name}"] = round(v[k]["bias_pct"], 1)
        row["mae_model"] = round(v["harmonized"]["mae"], 1)
        rows.append(row)
        print(row)

    t = pd.DataFrame(rows).sort_values("r2_model", ascending=False)
    out = ROOT / "outputs" / "tables" / "harmonization_validation.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(out, index=False)
    print("\n" + t.to_string(index=False) + f"\n-> {out.relative_to(ROOT)}")
