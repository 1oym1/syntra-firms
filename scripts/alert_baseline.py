"""Baselines for the early-alert and continuity panels on the story site -> site/alerts.js

Reads data/processed/clean_vegetation_Sudan.csv (clean vegetation fires, MODIS + one VIIRS per day)
and outputs/tables/run_info_Sudan.json, writes window.SYNTRA_ALERT.

Units: daily VIIRS detections. 2012 on is native VIIRS. 2000-2011 is MODIS put into VIIRS units with
one factor per calendar month, fitted on the 2012-2021 overlap (Terra-only months before Aqua get an
extra Terra -> Terra+Aqua factor fitted on 2003-2011). So the baseline covers all 26 fire seasons.

    .venv/bin/python scripts/alert_baseline.py
"""
import json, math, pathlib
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
G = 0.5                                    # grid size in degrees (~55 km)

f = pd.read_csv(ROOT / "data/processed/clean_vegetation_Sudan.csv",
                usecols=["latitude", "longitude", "acq_date", "satellite", "year", "month", "family", "frp", "daynight"])
f["date"] = pd.to_datetime(f["acq_date"])
last_full = f["date"].max().normalize() - pd.Timedelta(days=1)
f = f[f["date"] <= last_full]

# ---- national daily totals per family -------------------------------------------------------
day = f.groupby(["date", "family"]).size().unstack(fill_value=0)
day["MODIS"] = day.get("MODIS", 0); day["VIIRS"] = day.get("VIIRS", 0)
terra = f[f["satellite"] == "Terra"].groupby("date").size()
day["TERRA"] = terra.reindex(day.index, fill_value=0)
day["m"] = day.index.month; day["y"] = day.index.year

ov = day[(day.y >= 2012) & (day.y <= 2021) & (day.VIIRS > 0) & (day.MODIS > 0)]
k_mv = {int(k): float(v) for k, v in (ov.groupby("m").VIIRS.sum() / ov.groupby("m").MODIS.sum()).items()}          # MODIS -> VIIRS
ta = day[(day.y >= 2003) & (day.y <= 2011)]
k_ta = {int(k): float(v) for k, v in (ta.groupby("m").MODIS.sum() / ta.groupby("m").TERRA.sum()).items()}          # Terra -> Terra+Aqua

aqua_start = f.loc[f["satellite"] == "Aqua", "date"].min()
viirs_start = f.loc[f["family"] == "VIIRS", "date"].min()

def scale(date, month):
    """factor that puts one MODIS detection on this day into VIIRS units"""
    k = k_mv[month]
    return k * k_ta[month] if date < aqua_start else k

# ---- VIIRS-equivalent detections: VIIRS days as they are, MODIS days before VIIRS scaled ------
pre = f[(f["family"] == "MODIS") & (f["date"] < viirs_start)].copy()
pre["w"] = [scale(d, m) for d, m in zip(pre["date"], pre["month"])]
post = f[(f["family"] == "VIIRS") & (f["date"] >= viirs_start)].copy()
post["w"] = 1.0
eq = pd.concat([pre, post], ignore_index=True)
eq["gx"] = np.floor(eq["longitude"] / G).astype(int)
eq["gy"] = np.floor(eq["latitude"] / G).astype(int)

all_days = pd.date_range(f["date"].min().normalize(), last_full, freq="D")
days_in_m = {int(k): int(v) for k, v in pd.Series(all_days.month).value_counts().items()}        # how many days of each month we have
first_year, last_year = int(all_days[0].year), int(all_days[-1].year)

# ---- national: daily VIIRS-equivalent total, quantiles by month -----------------------------
nat = eq.groupby("date")["w"].sum().reindex(all_days, fill_value=0.0)
national = {}
for m in range(1, 13):
    v = nat[nat.index.month == m].values
    national[m] = [round(float(np.percentile(v, q)), 1) for q in range(0, 101)]

# ---- per cell: mean and 95th / 99th percentile of the daily count, by month --------------------
cd = eq.groupby(["gx", "gy", "month", "date"])["w"].sum().reset_index()
cells = {}
for (gx, gy, m), g in cd.groupby(["gx", "gy", "month"]):
    n = days_in_m[m]
    vals = np.sort(g["w"].values)[::-1]                       # non-zero days, largest first
    def pct(q):                                               # q-th percentile with the zero days included
        r = int(math.ceil((1 - q) * n))                       # rank from the top
        return float(vals[r - 1]) if r <= len(vals) else 0.0
    mean = vals.sum() / n
    cells.setdefault(f"{gx},{gy}", {})[int(m)] = [round(mean, 3), round(pct(.95), 1), round(pct(.99), 1),
                                            round(len(vals) / n, 3)]

# ---- continuity: daily VIIRS / MODIS ratio band by month (2012 on, days with >= 20 MODIS) ------
both = day[(day.index >= viirs_start) & (day.MODIS >= 20) & (day.VIIRS > 0)]
ratio = {}
for m in range(1, 13):
    r = (both[both.m == m].VIIRS / both[both.m == m].MODIS).values
    ratio[m] = ([round(float(np.percentile(r, q)), 2) for q in (10, 50, 90)] + [int(len(r))]) if len(r) >= 10 else None

# ---- fire character: VIIRS era, by month (night share, FRP) --------------------------------------
vi = f[f["family"] == "VIIRS"]
character = {}
for m in range(1, 13):
    g = vi[vi["month"] == m]
    character[m] = [round(float((g["daynight"] == "N").mean()), 3), round(float(g["frp"].median()), 1),
                    round(float(g["frp"].quantile(.9)), 1)]

# ---- weather: NASA POWER daily, 4 points across the fire belt, 2001-2025 -----------------------
import urllib.request
PTS = [(24.5, 12.0), (29.5, 11.0), (32.5, 12.5), (34.5, 11.8)]       # Darfur, S Kordofan, White Nile, Blue Nile
PAR = "RH2M,T2M,WS2M,PRECTOTCORR"
ext = ROOT / "data/external"; ext.mkdir(parents=True, exist_ok=True)
frames = []
for lon, lat in PTS:
    fp = ext / f"power_daily_{lon}_{lat}.json"
    if not fp.exists():
        url = (f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters={PAR}&community=AG"
               f"&longitude={lon}&latitude={lat}&start=20010101&end=20251231&format=JSON")
        fp.write_bytes(urllib.request.urlopen(url, timeout=180).read())
    p = json.loads(fp.read_text())["properties"]["parameter"]
    w = pd.DataFrame(p); w.index = pd.to_datetime(w.index, format="%Y%m%d"); w = w.replace(-999.0, np.nan)
    frames.append(w)
wx = sum(frames) / len(frames)                                       # fire-belt average
wx["doy"] = np.minimum(wx.index.dayofyear.values, 365)
weather = {}
for d in range(1, 366):                                              # +-7 day window across 25 years
    near = (np.abs(wx["doy"] - d) <= 7) | (np.abs(wx["doy"] - d) >= 358)
    g = wx[near]
    weather[d] = [round(float(g.RH2M.mean()), 1), round(float(g.RH2M.quantile(.1)), 1),
                  round(float(g.T2M.mean()), 1), round(float(g.WS2M.mean()), 2), round(float(g.WS2M.quantile(.9)), 2)]

# ---- handover numbers: exactly what the Streamlit app computes from its data pack ---------------
import sys
sys.path.insert(0, str(ROOT))
from syntra import apppack, datapack, series
from syntra import harmonize as hz
app = apppack.as_country(datapack.load("Sudan"))
cs = series.country_series(app["veg"], app["info"])
n20 = series.validate_n20(app["veg"], app["info"]["snpp_end"])
ho = cs["heldout"]
from syntra import analysis as an
_pk = datapack.load("Sudan")
_rw = an.risk_periods(an.daily_series(_pk["celldays"], _pk["factors"]))["weeks"]   # same as the site's risk clock
risk_weeks = [[r.week_start, round(float(r.share_of_years_pct)), r["class"]] for _, r in _rw.iterrows()]

out = {
    "grid": G, "from": str(all_days[0].date()), "to": str(last_full.date()),
    "years": last_year - first_year + 1,
    "k_modis_to_viirs": {m: round(k_mv[m], 3) for m in range(1, 13)},
    "k_terra_to_modis": {m: round(k_ta[m], 3) for m in range(1, 13)},
    "national": national, "cells": cells, "ratio": ratio, "character": character,
    "weather": weather, "weather_points": PTS, "risk_weeks": risk_weeks,
    "k_cells_modis_to_viirs": {int(m): round(float(k), 3) for m, k in cs["k_viirs"].items()},
    "bridges": {
        "terra_aqua": {"k": round(float(cs["k_terra_all"]), 3)},
        "modis_viirs": {"r2": round(float(ho["r2"]), 3), "r2_raw": round(float(ho["r2_raw_modis"]), 3),
                        "months": int(ho["n_months"]), "overlap": list(hz.OVERLAP)},
        "n20_snpp": {"k": round(n20["k"], 4), "r2": round(n20["r2"], 4), "n_months": n20["n_months"],
                     "years": n20["years"], "bias_pct": round(n20["bias_pct"], 3)},
        "snpp_last_day": str(app["info"]["snpp_end"].date()),
    },
}
js = "window.SYNTRA_ALERT=" + json.dumps(out, separators=(",", ":")) + ";\n"
(ROOT / "site/alerts.js").write_text(js)
print("cells", len(cells), "size", len(js) // 1024, "KB", "aqua", aqua_start.date(), "viirs", viirs_start.date())
print("k_mv", {m: round(v, 2) for m, v in k_mv.items()})
print("nov national p50/p90/p97.5", national[11][50], national[11][90], national[11][97])
print("nov ratio band", ratio[11]); print("char nov", character[11]); print("weather doy 316", weather[316])
