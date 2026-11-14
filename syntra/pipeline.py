"""Whole chain for one country, used by the app and the notebooks.

    from syntra.pipeline import load_country
    d = load_country("Sudan")
    d["cells"]      # ~1 km fire-cells per day, vegetation only, 2000 -> today (MODIS, S-NPP, NOAA-20)
    d["static"]     # hotspots flagged as static sources (for the map toggle)
    d["info"]       # dates, counts dropped, calibration factors

Steps: fetch yearly files (syntra.data) -> clean (syntra.clean, Step 3) -> add 2026 from the API
(syntra.recent, same cleaning) -> one static-source mask applied to ALL years -> fire-cells (syntra.harmonize).
"""
import contextlib
import datetime as dt
import io

import pandas as pd

from syntra import harmonize as hz
from syntra.clean import apply_static_mask, clean_all, static_mask
from syntra.data import fetch
from syntra.recent import load_recent

INSTS = ["modis", "viirs-snpp", "viirs-jpss1"]


def load_country(country, with_2026=True, quiet=True):
    out = io.StringIO() if quiet else None
    with (contextlib.redirect_stdout(out) if quiet else contextlib.nullcontext()):
        fetch(country, 2000, 2025)
        archive = clean_all(country, insts=INSTS)
        recent, info = load_recent(country, archive) if with_2026 else (archive.iloc[0:0], {"key": False})
        mask = static_mask(archive)
    fires = pd.concat([archive, recent], ignore_index=True) if len(recent) else archive
    flagged_by_type = int(fires["is_static"].sum())
    fires = apply_static_mask(fires, mask)
    cells = hz.fire_cells(fires, sensors=("MODIS", hz.REFERENCE, hz.NOAA20))
    snpp_end = pd.Timestamp(info["snpp_last_day"]) if info.get("snpp_last_day") else None
    last_day = cells["date"].max()
    # Today's data is still arriving: only count up to yesterday
    complete_day = min(last_day, pd.Timestamp(dt.date.today() - dt.timedelta(days=1)))
    cells = cells[cells["date"] <= complete_day]
    info.update({
        "rows_clean": len(fires),
        "static_by_type": flagged_by_type,
        "static_by_mask": int(fires["is_static"].sum()) - flagged_by_type,
        "mask_cells": len(mask),
        "complete_day": complete_day,
        "snpp_end": snpp_end,
        "k_noaa20": hz.fit_noaa20(cells, snpp_end),
        "terra_k": hz.terra_factors(cells),
    })
    static = fires.loc[fires["is_static"], ["latitude", "longitude", "acq_date", "satellite", "frp", "type"]]
    return {"cells": cells, "static": static.reset_index(drop=True), "info": info}
