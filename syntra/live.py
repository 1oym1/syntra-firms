"""Hotspots for the map: live view (FIRMS API, last 1-10 days) and historical view (data pack).

Both views return the same columns and pass through the same toggles:
    sensors          any of "MODIS", "VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21"
    include_static   False = vegetation fires only (filtered), True = static heat sources too (unfiltered)

    from syntra import live, datapack
    pts = live.live_points(days=2, sensors=["MODIS", "VIIRS_NOAA20"], include_static=False)
    pack = datapack.load("Sudan")
    old = live.historical_points(pack, "2025-11-01", "2025-11-30", sensors=["VIIRS_SNPP"])

The live view is cleaned with the same rules as the archive (syntra.clean) and the static mask
built from the archive, because near-real-time rows have no `type` field. Live data are cached on
disk for an hour. Errors never show the request URL, since it holds the MAP_KEY.
"""
import datetime as dt
import io
import time

import pandas as pd
import requests

from syntra import nrt
from syntra.clean import apply_static_mask, clean_file, country_shape
from syntra.data import DEFAULT_COUNTRY, PROCESSED_DIR, RAW_DIR

LIVE_SOURCES = {"MODIS": "MODIS_NRT", "VIIRS_SNPP": "VIIRS_SNPP_NRT",
                "VIIRS_NOAA20": "VIIRS_NOAA20_NRT", "VIIRS_NOAA21": "VIIRS_NOAA21_NRT"}
INST = {"MODIS": "modis", "VIIRS_SNPP": "viirs-snpp", "VIIRS_NOAA20": "viirs-jpss1", "VIIRS_NOAA21": "viirs-jpss2"}
SATELLITE = {"MODIS": None, "VIIRS_SNPP": "N", "VIIRS_NOAA20": "N20", "VIIRS_NOAA21": "N21"}
DEFAULT_SENSORS = ("MODIS", "VIIRS_NOAA20")          # S-NPP stopped on 2 Nov 2026
LIVE_DIR = RAW_DIR / "live"
TTL_SECONDS = 3600
MAX_DAYS = 10                                        # two API calls of 5 days
COLUMNS = ["latitude", "longitude", "acq_date", "acq_time", "time_utc", "satellite", "sensor", "frp",
           "daynight", "is_static"]

_shape, _mask = {}, {}


def filter_points(pts, sensors=DEFAULT_SENSORS, include_static=False):
    """The map toggles: keep the chosen sensors, and drop static heat sources unless asked for."""
    keep = pts.sensor.isin(list(sensors))
    if not include_static:
        keep &= ~pts.is_static
    return pts[keep].reset_index(drop=True)


def _country(country):
    if country not in _shape:
        _shape[country] = country_shape(country)
        _mask[country] = pd.read_csv(PROCESSED_DIR / f"static_mask_{country}.csv")
    return _shape[country], _mask[country]


def _fetch(source, bbox, days, end_day, key):
    """One FIRMS area call (at most 5 days up to end_day), cached on disk for TTL_SECONDS."""
    path = LIVE_DIR / f"{source}_{end_day:%Y%m%d}_{days}d_{bbox.replace(',', '_')}.csv"
    if path.exists() and time.time() - path.stat().st_mtime < TTL_SECONDS:
        return path
    start = end_day - dt.timedelta(days=days - 1)
    url = f"{nrt.API}/area/csv/{key}/{source}/{bbox}/{days}/{start:%Y-%m-%d}"
    try:
        r = requests.get(url, timeout=(15, 120))
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"FIRMS did not answer for {source} ({type(e).__name__}).") from None
    if r.text.lstrip().lower().startswith(("invalid", "error")):
        raise RuntimeError(f"FIRMS refused the request for {source} (check the MAP_KEY).")
    df = pd.read_csv(io.StringIO(r.text))
    if "type" not in df:
        df["type"] = nrt.UNKNOWN_TYPE                  # NRT has no type: the static mask decides
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    df.to_csv(tmp, index=False)
    tmp.replace(path)
    return path


def live_points(days=2, sensors=DEFAULT_SENSORS, include_static=False, country=DEFAULT_COUNTRY, today=None):
    """Hotspots of the last `days` days (1-10) from FIRMS near-real-time, cleaned like the archive."""
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days must be 1-{MAX_DAYS}")
    key = nrt.map_key()
    shape, mask = _country(country)
    bbox = nrt._bbox(shape)
    today = today or dt.datetime.now(dt.timezone.utc).date()
    parts = []
    for sensor in sensors:
        left, end = days, today
        while left > 0:                                 # the API gives at most 5 days per call
            n = min(left, nrt.DAYS_PER_CALL)
            df = clean_file(_fetch(LIVE_SOURCES[sensor], bbox, n, end, key), INST[sensor], shape)
            df = apply_static_mask(df, mask) if not df.empty else df
            if "is_static" in df and len(df):
                df["is_static"] |= df["type"].isin([1, 2, 3])
            df["sensor"] = sensor
            parts.append(df)
            left, end = left - n, end - dt.timedelta(days=n)
    pts = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLUMNS)
    return _finish(filter_points(pts, sensors, include_static))


def historical_points(pack, start, end, sensors=("MODIS", "VIIRS_SNPP", "VIIRS_NOAA20"), include_static=False):
    """Hotspots between two dates (inclusive) from the data pack."""
    p = pack["points"]
    p = p[(p.acq_date >= pd.Timestamp(start)) & (p.acq_date <= pd.Timestamp(end))]
    return _finish(filter_points(p, sensors, include_static))


def _finish(pts):
    pts = pts.copy()
    if pts.empty:
        return pd.DataFrame(columns=COLUMNS)
    pts["acq_date"] = pd.to_datetime(pts.acq_date)
    pts["time_utc"] = pts.acq_date + pd.to_timedelta(pts.acq_time // 100, "h") + pd.to_timedelta(pts.acq_time % 100, "m")
    return pts[COLUMNS].sort_values("time_utc").reset_index(drop=True)


def counts(pts):
    """Numbers above the map: hotspots per sensor, static ones apart."""
    if pts.empty:
        return pd.DataFrame(columns=["sensor", "fires", "static"])
    g = pts.groupby("sensor", observed=True).is_static
    return pd.DataFrame({"fires": (~pts.is_static).groupby(pts.sensor, observed=True).sum(),
                         "static": g.sum()}).reset_index()
