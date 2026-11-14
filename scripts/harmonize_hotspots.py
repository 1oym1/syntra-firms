"""
Step 3 – MODIS / VIIRS hotspot harmonization (SYNTRA – NASA Space Apps 2026)

- Isolates static sources (volcanoes, gas flares, offshore) instead of dropping them
- Aggregates fires onto a common 0.1° grid (fire-active cell-days per month)
- Calibrates MODIS -> VIIRS-equivalent on the 2012+ overlap and validates on held-out years

Inputs : modis.csv, viirs.csv  (FIRMS archive/standard files – must include the 'type' column)
Outputs: static_sources.csv, static_monthly.csv, harmonized_monthly.csv
"""
import pandas as pd
import numpy as np

# ---------- 1) Load ----------
modis = pd.read_csv("modis.csv")
viirs = pd.read_csv("viirs.csv")

# FIRMS 'type' codes:
# 0 = presumed vegetation fire | 1 = active volcano
# 2 = other static land source (gas flares, industry) | 3 = offshore (oil/gas platforms)
TYPE_LABELS = {0: "vegetation_fire", 1: "volcano", 2: "static_land", 3: "offshore"}


def split_sources(df, sensor):
    df = df.copy()
    df["sensor"] = sensor
    df["source_class"] = df["type"].map(TYPE_LABELS).fillna("unknown")
    fires = df[df["type"] == 0]
    static = df[df["type"] != 0]  # volcanoes, gas flares, offshore, unknown
    return fires, static


modis_fires, modis_static = split_sources(modis, "MODIS")
viirs_fires, viirs_static = split_sources(viirs, "VIIRS")

# Save static sources for later use
static_all = pd.concat([modis_static, viirs_static], ignore_index=True)
static_all.to_csv("static_sources.csv", index=False)
print("Static sources saved:", static_all["source_class"].value_counts().to_dict())

# ---------- 2) Confidence filter (fires only) ----------
modis_fires = modis_fires[modis_fires["confidence"] >= 30]
viirs_fires = viirs_fires[
    viirs_fires["confidence"].astype(str).str.lower().str[0].isin(["n", "h"])
]

# ---------- 3) Common grid (0.1°) + fire-active cell-days per month ----------
RES = 0.1


def grid_monthly(df, sensor):
    df = df.copy()
    df["acq_date"] = pd.to_datetime(df["acq_date"])
    df["cell"] = (
        np.floor(df["latitude"] / RES).astype(int).astype(str)
        + "_"
        + np.floor(df["longitude"] / RES).astype(int).astype(str)
    )
    daily = df.drop_duplicates(["acq_date", "cell"])
    return daily.groupby(daily["acq_date"].dt.to_period("M")).size().rename(sensor)


ts = pd.concat(
    [grid_monthly(modis_fires, "modis"), grid_monthly(viirs_fires, "viirs")], axis=1
).fillna(0)

# Same for static sources (kept separate, not harmonized)
static_ts = pd.concat(
    [grid_monthly(modis_static, "modis_static"), grid_monthly(viirs_static, "viirs_static")],
    axis=1,
).fillna(0)
static_ts.to_csv("static_monthly.csv")

# ---------- 4) Calibrate on overlap (2012+), hold out last 2 years ----------
overlap = ts[(ts.index.year >= 2012) & (ts["viirs"] > 0)]
cutoff = overlap.index.year.max() - 2
train = overlap[overlap.index.year <= cutoff]
test = overlap[overlap.index.year > cutoff]

slope, intercept = np.polyfit(train["modis"], train["viirs"], 1)
print(f"VIIRS ≈ {slope:.2f} × MODIS + {intercept:.2f}")

# ---------- 5) Harmonized series ----------
ts["modis_as_viirs"] = (slope * ts["modis"] + intercept).clip(lower=0)
ts["harmonized"] = np.where(ts.index.year >= 2012, ts["viirs"], ts["modis_as_viirs"])
ts.to_csv("harmonized_monthly.csv")

# ---------- 6) Validation ----------
pred = slope * test["modis"] + intercept
rmse = np.sqrt(((pred - test["viirs"]) ** 2).mean())
r2 = np.corrcoef(pred, test["viirs"])[0, 1] ** 2
print(f"Test RMSE: {rmse:.1f} | R²: {r2:.2f}")
