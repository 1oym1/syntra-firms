"""The app's data (veg, static, info) from a data pack (syntra.datapack).

The app used to rebuild everything from the FIRMS yearly files and the API (about 45 s, or minutes on a
fresh machine). A data pack loads in under a second and needs no download, so the app can run online.

    from syntra import datapack, apppack
    d = apppack.as_country(datapack.load("Sudan"))   # same keys as pipeline.load_country

The pack's points are cut at the last complete day, and the static mask is applied the same way
pipeline.load_country does it, so the app's numbers do not change.
"""
import numpy as np
import pandas as pd

from syntra import series
from syntra.clean import GRID_DEG, apply_static_mask, cell_id

MODIS_SATS = ("Terra", "Aqua")


def as_country(pack):
    m = pack["manifest"]
    complete_day = pd.Timestamp(m["data_to"])
    pts = pack["points"]
    pts = pts[pts.acq_date <= complete_day].drop(columns="sensor")
    for c in ("satellite", "daynight"):
        pts[c] = pts[c].astype(str)
    n_by_type = int(pts.is_static.sum())
    pts = apply_static_mask(pts, pack["static_mask"])

    veg = pts[~pts.is_static].copy()
    veg["type"] = 0
    veg["year"] = veg.acq_date.dt.year
    veg["month"] = veg.acq_date.dt.month
    veg["cell_id"] = cell_id(veg.latitude, veg.longitude, GRID_DEG)
    veg["family"] = np.where(veg.satellite.isin(MODIS_SATS), "MODIS", "VIIRS")
    veg = veg.reset_index(drop=True)

    static = pts[pts.is_static][["latitude", "longitude", "acq_date", "satellite", "frp"]].reset_index(drop=True)

    snpp = m.get("sensors", {}).get("VIIRS_SNPP", {}).get("to")
    snpp_end = pd.Timestamp(snpp) if snpp else None
    info = {
        "key": True,                     # the pack was built with this year's FIRMS API data
        "pack_built_utc": m.get("built_utc"),
        "snpp_last_day": snpp_end,
        "rows_clean": len(pts),
        "static_by_type": n_by_type,
        "static_by_mask": int(pts.is_static.sum()) - n_by_type,
        "mask_cells": len(pack["static_mask"]),
        "complete_day": complete_day,
        "snpp_end": snpp_end,
        "k_n20": series.fit_n20(veg, snpp_end),
    }
    return {"veg": veg, "static": static, "info": info}
