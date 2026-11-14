"""Whole chain for one country, used by the app and the notebooks.

    from syntra.pipeline import load_country
    d = load_country("Sudan")
    d["veg"]        # clean vegetation fires 2000 -> yesterday (MODIS, VIIRS S-NPP, VIIRS NOAA-20)
    d["static"]     # hotspots flagged as static sources (for the map toggle)
    d["info"]       # dates, counts, NOAA-20 factor

or save everything to data/processed/ from the repo root:

    python -m syntra.pipeline --country Sudan

Steps: fetch yearly files (syntra.data) -> clean inside the border (syntra.clean, Step 3) -> add this year
from the FIRMS API (syntra.nrt, same cleaning) -> one static-source mask applied to ALL years.
Harmonization (Steps 4-5) is syntra.harmonize; syntra.series extends it to 2026 for the app.
"""
import argparse
import contextlib
import datetime as dt
import io
import json

import pandas as pd

from syntra import nrt, series
from syntra.clean import apply_static_mask, clean_all, country_shape, static_mask
from syntra.data import DEFAULT_COUNTRY, PROCESSED_DIR, fetch

INSTS = ["modis", "viirs-snpp", "viirs-jpss1"]


NRT_CACHE_HOURS = 3      # near-real-time data is re-read from the FIRMS API at most every 3 hours


def this_year(country, year, mask, archive):
    """This year's clean hotspots from syntra.nrt (all three sensors), or none without a MAP_KEY.

    The cleaned result is kept on disk (data/processed/cache/) for NRT_CACHE_HOURS, so restarting the app does
    not call the FIRMS API again (that call is most of a cold start: ~35 s for Sudan)."""
    try:
        nrt.map_key()
    except RuntimeError:
        return archive.iloc[0:0], {"key": False, "snpp_last_day": None}
    cache = PROCESSED_DIR / "cache" / f"nrt_{country}_{year}.parquet"
    stamp = cache.with_suffix(".json")
    mask_id = str(int(pd.util.hash_pandas_object(mask, index=False).sum()))
    if cache.exists() and stamp.exists():
        meta = json.loads(stamp.read_text())
        age_h = (dt.datetime.now() - dt.datetime.fromisoformat(meta["saved"])).total_seconds() / 3600
        if age_h < NRT_CACHE_HOURS and meta.get("mask") == mask_id and meta.get("archive_last") == str(archive.year.max()):
            fires = pd.read_parquet(cache)
            return fires, {"key": True, "snpp_last_day": meta.get("snpp_last_day")}
    fires, info = _this_year_api(country, year, mask, archive)
    cache.parent.mkdir(parents=True, exist_ok=True)
    fires.to_parquet(cache, index=False)
    stamp.write_text(json.dumps({"saved": dt.datetime.now().isoformat(), "mask": mask_id,
                                 "archive_last": str(archive.year.max()),
                                 "snpp_last_day": str(info["snpp_last_day"]) if info["snpp_last_day"] is not None
                                 else None}))
    return fires, info


def _this_year_api(country, year, mask, archive):
    # nrt reads the static mask from this file (the same mask clean.run writes)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    mask.to_csv(PROCESSED_DIR / f"static_mask_{country}.csv", index=False)
    fires, _ = nrt.run(country, year)
    fires = fires.drop(columns=["sensor", "type_known"], errors="ignore")
    fires = fires[fires.year > archive.year.max()]        # never count a year twice
    snpp = fires.loc[fires.satellite == series.SNPP, "acq_date"]
    return fires, {"key": True, "snpp_last_day": snpp.max() if len(snpp) else None}


def load_country(country, with_2026=True, quiet=True):
    out = io.StringIO() if quiet else None
    year = dt.date.today().year          # yearly files exist up to last year; this year comes from the API
    with (contextlib.redirect_stdout(out) if quiet else contextlib.nullcontext()):
        fetch(country, 2000, year - 1)
        shape = country_shape(country)  # Natural Earth 1:10m border, same clip for archive and this year
        archive = clean_all(country, insts=INSTS, shape=shape)
        mask = static_mask(archive)
        recent, info = this_year(country, year, mask, archive) if with_2026 else (archive.iloc[0:0], {"key": False})
    fires = pd.concat([archive, recent], ignore_index=True) if len(recent) else archive
    flagged_by_type = int(fires["is_static"].sum())
    fires = apply_static_mask(fires, mask)
    # Today's data is still arriving: only count up to yesterday
    complete_day = min(fires["acq_date"].max(), pd.Timestamp(dt.date.today() - dt.timedelta(days=1)))
    fires = fires[fires["acq_date"] <= complete_day]
    veg = fires[~fires["is_static"]].reset_index(drop=True)
    snpp_end = pd.Timestamp(info["snpp_last_day"]) if info.get("snpp_last_day") else None
    info.update({
        "rows_clean": len(fires),
        "static_by_type": flagged_by_type,
        "static_by_mask": int(fires["is_static"].sum()) - flagged_by_type,
        "mask_cells": len(mask),
        "complete_day": complete_day,
        "snpp_end": snpp_end,
        "k_n20": series.fit_n20(veg, snpp_end),
    })
    static = fires.loc[fires["is_static"], ["latitude", "longitude", "acq_date", "satellite", "frp", "type"]]
    return {"veg": veg, "static": static.reset_index(drop=True), "info": info}


def one_viirs(veg, snpp_end):
    """MODIS + one VIIRS satellite per day: Suomi NPP up to its last day, NOAA-20 after it (as syntra.nrt)."""
    if snpp_end is None:
        return veg[veg.satellite != series.N20]
    viirs_ok = ((veg.satellite == series.SNPP) & (veg.acq_date <= snpp_end)) | \
               ((veg.satellite == series.N20) & (veg.acq_date > snpp_end))
    return veg[(veg.family == "MODIS") | viirs_ok]


def save(country=DEFAULT_COUNTRY, out_dir=PROCESSED_DIR):
    """Clean + harmonize one country (archive and 2026) and write the results to data/processed/.

    clean_vegetation_<country>.csv           clean vegetation fires 2000 -> yesterday, MODIS + one VIIRS per day
    clean_vegetation_all_sensors_<country>.parquet   the same with both VIIRS satellites (for checks)
    static_sources_<country>.csv             hotspots flagged as static (type 1-3 or the mask)
    harmonized_<country>.csv                 monthly burned 0.1 deg cells, harmonized, to the last full month
    factors_<country>.csv, validation_<country>.csv, run_info_<country>.json
    """
    from syntra import harmonize as hz
    d = load_country(country, quiet=False)
    veg, info = d["veg"], d["info"]
    cs = series.country_series(veg, info)
    veg.to_parquet(out_dir / f"clean_vegetation_all_sensors_{country}.parquet", index=False)
    # harmonize.run reads this file: MODIS + ONE VIIRS satellite per day (S-NPP to its last day, NOAA-20
    # after), the same rule as syntra.nrt, so VIIRS cells are never counted from two satellites at once
    one_viirs(veg, info["snpp_end"]).to_csv(out_dir / f"clean_vegetation_{country}.csv", index=False)
    d["static"].to_csv(out_dir / f"static_sources_{country}.csv", index=False)
    cs["tab"].to_csv(out_dir / f"harmonized_{country}.csv", index=False)
    pd.DataFrame({"month": range(1, 13), "terra_to_terra_aqua": cs["k_terra"].round(3).values,
                  "modis_to_viirs": cs["k_viirs"].round(3).values}).to_csv(out_dir / f"factors_{country}.csv",
                                                                           index=False)
    cs["validation"].to_csv(out_dir / f"validation_{country}.csv", index=False)
    n20 = series.validate_n20(veg, info["snpp_end"])
    summary = {
        "country": country, "complete_day": str(info["complete_day"].date()),
        "last_full_month": str(series.last_full_month(info["complete_day"])),
        "snpp_last_day": str(info["snpp_end"].date()) if info["snpp_end"] is not None else None,
        "rows_clean": info["rows_clean"], "rows_vegetation": len(veg),
        "static_by_type": info["static_by_type"], "static_by_mask": info["static_by_mask"],
        "mask_cells": info["mask_cells"],
        "rows_by_satellite": {k: int(v) for k, v in veg.satellite.value_counts().items()},
        "k_terra_annual": round(cs["k_terra_all"], 3), "k_modis_to_viirs_annual": round(cs["k_viirs_all"], 3),
        "heldout_r2": round(cs["heldout"]["r2"], 3), "heldout_r2_raw_modis": round(cs["heldout"]["r2_raw_modis"], 3),
        "median_abs_annual_error_pct": float(cs["validation"]["annual_error_%"].abs().median()),
        "n20_to_snpp": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in (n20 or {}).items()},
        "overlap_years": list(hz.OVERLAP),
    }
    (out_dir / f"run_info_{country}.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    print(f"\nSaved to {out_dir}")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Clean + harmonize one country, 2000 to yesterday, into data/processed/.")
    ap.add_argument("--country", default=DEFAULT_COUNTRY)
    save(ap.parse_args().country)
