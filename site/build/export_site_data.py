"""Exports the real numbers the story page (site/index.html) draws: python site/build/export_site_data.py
Writes site/data.js (window.SYNTRA = {...})."""
import json, pathlib, sys
import numpy as np, pandas as pd, geopandas as gpd
import shapely
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from syntra import datapack, apppack, series, analysis as an, live
from syntra.clean import BORDERS_FILE, country_shape

out = {}
# land dot-matrix for the globe
world = gpd.read_file(BORDERS_FILE).to_crs(4326)
land = shapely.union_all(world.geometry.values).buffer(0)
shapely.prepare(land)
step = 1.3
lats = np.arange(-58, 78, step); dots = []
for la in lats:
    n = max(8, int(round(360 / step * np.cos(np.radians(la)))))
    lons = np.linspace(-180, 180, n, endpoint=False)
    keep = shapely.contains_xy(land, lons, np.full_like(lons, la))
    dots += [[round(float(lo), 2), round(float(la), 2)] for lo in lons[keep]]
out["land"] = dots
sd = country_shape("Sudan").simplify(0.04)
geoms = getattr(sd, "geoms", [sd])
big = max(geoms, key=lambda g: g.area)
out["border"] = [[round(x, 3), round(y, 3)] for x, y in big.exterior.coords]

pack = datapack.load()
cd = pack["celldays"]
recent = cd[(cd.family == "VIIRS") & (cd.year.between(2016, 2025))]
cnt = recent.groupby("cell_id").size().sort_values(ascending=False)
top = cnt.head(7000)
cent = datapack.cell_centre(top.index.values)
lat, lon = (cent if isinstance(cent, tuple) else (cent[0], cent[1]))
out["cells"] = [[round(float(a), 2), round(float(b), 2), int(c)] for a, b, c in zip(lon, lat, top.values)]

try:
    lp = live.live_points(days=7, sensors=list(live.LIVE_SOURCES), include_static=False)
    out["live_total"] = int(len(lp)); out["live_by_sensor"] = {k: int(v) for k, v in lp.sensor.value_counts().items()}
    out["live_from"], out["live_to"] = str(lp.acq_date.min().date()), str(lp.acq_date.max().date())
    s = lp.sample(min(2600, len(lp)), random_state=1)
    out["live"] = [[round(float(a), 2), round(float(b), 2), k] for a, b, k in zip(s.longitude, s.latitude, s.sensor)]
except Exception as e:  # noqa: BLE001
    print("live skipped:", type(e).__name__); out["live"] = []

d = apppack.as_country(pack)
cs = series.country_series(d["veg"], d["info"])
h = cs["tab"]
S = lambda c: series.as_series(h, c)
harm, mod, vii = S("harmonized_cells"), S("modis_cells"), S("viirs_cells")
months = [str(p) for p in harm.index]
out["months"] = months
out["harm"] = [None if not np.isfinite(v) else round(float(v)) for v in harm.values]
raw = mod.where(mod.index < pd.Period("2012-02", "M"), vii)
out["raw"] = [None if not np.isfinite(v) else round(float(v)) for v in raw.values]
out["heldout_r2"], out["raw_r2"] = round(cs["heldout"]["r2"], 3), round(cs["heldout"]["r2_raw_modis"], 2)
out["data_to"] = str(d["info"]["complete_day"].date())

daily = an.daily_series(pack["celldays"], pack["factors"])
rp = an.risk_periods(daily)
w = rp["weeks"]
out["risk"] = {"weeks": [[r.week_start, round(float(r.share_of_years_pct)), r["class"], round(float(r["median"]))] for _, r in w.iterrows()],
               "periods": rp["periods"], "per_decade": round(rp["high_weeks_per_decade"], 1), "years": list(rp["years"])}
pathlib.Path(__file__).resolve().parents[1].joinpath("data.js").write_text("window.SYNTRA=" + json.dumps(out, separators=(",", ":")) + ";\n")
print({k: (len(v) if isinstance(v, list) else v) for k, v in out.items() if k != "risk"}, rp["periods"][:2], rp["high_weeks_per_decade"])
