"""Early warning and continuity checks, the same rules as the story site (site/index.html).

Is today's fire activity normal for this time of year? Today's VIIRS detections (last 24 h before the
newest pass) are compared with every past day of the same month since 2000 (site/alerts.js, made by
scripts/alert_baseline.py), area by area on a 0.5 degree grid, plus fire type and NASA POWER weather.
The site and the app read the same baseline file, so they make the same call.
"""
import datetime as dt
import json
import pathlib

import numpy as np
import pandas as pd
import requests

BASELINE = pathlib.Path(__file__).resolve().parents[1] / "site" / "alerts.js"
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMS = ["RH2M", "T2M", "WS2M", "PRECTOTCORR"]
KIND = {"surge": "Surge", "rare": "Fire where it is rare", "above": "Above normal"}
LEVELS = [("Expected seasonal burning", "Fires match what this season normally brings. Routine monitoring is enough; no area stands out."),
          ("Watch", "Something is off the normal pattern. Check the areas below with local contacts and look again after the next satellite pass."),
          ("Warning", "Several signals are above normal at once. Prioritise ground checks in the areas below today and alert local civil defence."),
          ("Severe", "Fire activity and fire weather are far outside the normal range. Treat the areas below as urgent.")]
TOWNS = [("Khartoum", 32.56, 15.5), ("Wad Madani", 33.52, 14.4), ("Sennar", 33.62, 13.55), ("Ed Damazin", 34.36, 11.79),
         ("Kurmuk", 34.28, 10.55), ("Kosti", 32.66, 13.16), ("El Obeid", 30.22, 13.18), ("Um Ruwaba", 31.22, 12.9),
         ("Rashad", 31.06, 11.86), ("Kadugli", 29.72, 11.01), ("Talodi", 30.38, 10.63), ("Dilling", 29.65, 12.05),
         ("Al Fula", 28.35, 11.73), ("Babanusa", 27.81, 11.33), ("En Nahud", 28.43, 12.7), ("Ed Daein", 26.13, 11.46),
         ("Nyala", 24.88, 12.05), ("El Fasher", 25.35, 13.63), ("Kutum", 24.67, 14.2), ("Zalingei", 23.47, 12.91),
         ("Geneina", 22.45, 13.45), ("Gedaref", 35.38, 14.03), ("Kassala", 36.4, 15.45), ("Port Sudan", 37.22, 19.62),
         ("Atbara", 33.98, 17.7), ("Dongola", 30.48, 19.17)]


def load_baseline(path=BASELINE):
    txt = pathlib.Path(path).read_text()
    return json.loads(txt[txt.index("=") + 1:].strip().rstrip(";"))


def near(lon, lat):
    """'Around X', 'N km from X' (nearest town within 260 km) or 'Remote area'."""
    def km(t):
        r = np.pi / 180
        x = (t[1] - lon) * r * np.cos((lat + t[2]) / 2 * r)
        return 6371 * np.hypot(x, (t[2] - lat) * r)
    t = min(TOWNS, key=km)
    d = km(t)
    return f"Around {t[0]}" if d < 25 else f"{int(round(d / 5) * 5)} km from {t[0]}" if d < 260 else "Remote area"


def weather(days=14, points=None, timeout=12):
    """NASA POWER daily RH, T, wind and rain at 2 m, mean of the fire-belt points; only days every point has."""
    points = points or load_baseline()["weather_points"]
    end = dt.datetime.now(dt.timezone.utc).date()
    start = end - dt.timedelta(days=days)
    got = []
    for lon, lat in points:
        try:
            r = requests.get(POWER_URL, timeout=timeout, params={
                "parameters": ",".join(POWER_PARAMS), "community": "AG", "longitude": lon, "latitude": lat,
                "start": f"{start:%Y%m%d}", "end": f"{end:%Y%m%d}", "format": "JSON"})
            r.raise_for_status()
            got.append(pd.DataFrame(r.json()["properties"]["parameter"]))
        except Exception:  # noqa: BLE001 - one point missing still leaves a mean of the others
            continue
    if not got:
        return pd.DataFrame(columns=POWER_PARAMS)
    df = pd.concat(got, keys=range(len(got))).replace(-999, np.nan)
    ok = df.groupby(level=1).count().min(axis=1) == len(got)
    out = df.groupby(level=1).mean()[ok]
    out.index = pd.to_datetime(out.index, format="%Y%m%d")
    return out.sort_index()


def last_24h(points):
    """Clean, non-static live points in the 24 h before the newest pass (FIRMS '24h' files hold older passes too)."""
    p = points[~points["is_static"].astype(bool)] if "is_static" in points else points
    if p.empty:
        return p
    return p[p.time_utc > p.time_utc.max() - pd.Timedelta(hours=24)]


def _pct(q, v):
    i = 0
    while i < 100 and q[i + 1] <= v:
        i += 1
    return i


def _doy(d):
    return min(365, pd.Timestamp(d).dayofyear)


def call(points, A=None, wx=None, now=None):
    """The early-warning call. points: live hotspots (syntra.live.live_points); wx: weather() or None.

    Returns level (0-3), name, advice, sensor, n, factors [(name, value, detail, status, tag)] and
    areas (flagged 0.5 degree squares, worst first) and cells (every burning square today)."""
    A = A or load_baseline()
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    now = now.tz_convert(None) if now.tzinfo else now
    m = now.month
    M = str(m)
    G = A["grid"]
    mon, monl = now.strftime("%b"), now.strftime("%B")
    factors, score = [], 0
    wk = A["risk_weeks"][min(51, (now.dayofyear - 1) // 7)]
    factors.append(("Season", f"Week of {wk[0]}: a high-fire week in {wk[1]}% of years",
                    "Peak burning season, so many fires are expected. The rows below say whether today is unusual "
                    "even for this season." if wk[1] >= 50 else "Outside the main burning season, so even a modest rise stands out.",
                    "na", f"{wk[2]} season"))
    p = last_24h(points)
    by_sensor = p.sensor.value_counts().to_dict() if len(p) else {}
    sensor = "VIIRS_NOAA20" if by_sensor.get("VIIRS_NOAA20", 0) > 0 else "VIIRS_NOAA21"
    v = p[p.sensor == sensor]
    n = len(v)
    q = A["national"][M]
    P = _pct(q, n)
    fl = 3 if P >= 97 else 2 if P >= 90 else 1 if P >= 75 else 0
    score += fl
    sfx = {1: "st", 2: "nd", 3: "rd"}.get(P % 10 if P % 100 not in (11, 12, 13) else 0, "th")
    factors.append(("Fire count", f"{n:,} detections in 24 h",
                    f"{P}{sfx} percentile of {monl} days since {A['from'][:4]} · a typical day has {q[50]:,.0f}",
                    ["ok", "mid", "hi", "hi"][fl], ["Normal", "Above normal", "High", "Extreme"][fl]))
    # areas
    gx, gy = np.floor(v.longitude / G).astype(int), np.floor(v.latitude / G).astype(int)
    cnt = pd.Series(1, index=pd.MultiIndex.from_arrays([gx, gy])).groupby(level=[0, 1]).size() if n else pd.Series(dtype=int)
    cells = []
    for (x, y), c in cnt.items():
        b = A["cells"].get(f"{x},{y}", {}).get(M, [0, 0, 0, 0])
        kind = "rare" if c >= 3 and b[3] < .05 else "surge" if c >= 5 and c > b[2] else "above" if c >= 5 and c > b[1] else None
        cells.append(dict(gx=x, gy=y, n=int(c), mean=b[0], p95=b[1], p99=b[2], share=b[3], kind=kind, excess=c - b[0],
                          lon=(x + .5) * G, lat=(y + .5) * G))
    rank = {"surge": 0, "rare": 1, "above": 2}
    flagged = sorted([c for c in cells if c["kind"]], key=lambda c: (rank[c["kind"]], -c["excess"]))
    nsurge = sum(c["kind"] != "above" for c in flagged)
    al = 3 if nsurge >= 3 else 2 if nsurge >= 1 else 1 if len(flagged) >= 3 else 0
    score += al
    factors.append(("Areas", f"{len(flagged)} of {len(cells)} burning areas above their normal" if flagged
                    else f"All {len(cells)} burning areas within their normal",
                    f"{nsurge} with a surge or fire where it is rare · areas are {G}° squares (about 55 km)" if flagged
                    else f"each area compared with its own {monl} history",
                    ["ok", "mid", "hi", "hi"][al], ["Normal", "Watch", "Unusual", "Widespread"][al]))
    # fire type: Sudan local time (UTC+2) for day and night
    C = A["character"][M]
    if n:
        h = (v.time_utc.dt.hour + v.time_utc.dt.minute / 60 + 2) % 24
        night = float(((h < 6) | (h >= 18)).mean())
        frp = float(v.frp.dropna().median()) if v.frp.notna().any() else None
    else:
        night, frp = 0.0, None
    intense = (frp is not None and frp > 1.5 * C[1]) or night > max(.35, 2 * C[0])
    score += int(intense)
    factors.append(("Fire type", f"Median fire power {frp:.1f} MW, {round(night * 100)}% at night" if frp is not None
                    else f"Median fire power n/a, {round(night * 100)}% at night",
                    f"normal for {mon}: {C[1]} MW, {round(C[0] * 100)}% at night. Small daytime fires point to crop and grass burning.",
                    "mid" if intense else "ok", "More intense" if intense else "Typical burning"))
    # weather: last 3 POWER days against the 2001-2025 normal for the same days of the year
    if wx is not None and len(wx):
        last = wx.tail(3)
        base = np.array([A["weather"][str(_doy(d))] for d in last.index])
        rh, t, ws = last.RH2M.mean(), last.T2M.mean(), last.WS2M.mean()
        rhN, rhP10, tN, wsP90 = base[:, 0].mean(), base[:, 1].mean(), base[:, 2].mean(), base[:, 4].mean()
        dry = 2 if rh <= rhP10 else 1 if rh < rhN - 5 else 0
        windy = ws > wsP90
        score += dry + int(windy)
        span = f"{last.index[0]:%d}–{last.index[-1]:%d %b}"
        factors.append(("Humidity", f"{rh:.0f}% relative humidity",
                        f"{span} · normal for these days {rhN:.0f}% · fire belt, NASA POWER",
                        ["ok", "mid", "hi"][dry], ["Normal", "Drier", "Much drier"][dry]))
        factors.append(("Wind, heat", f"{ws:.1f} m/s wind, {t:.1f} °C",
                        f"normal {base[-1, 3]:.1f} m/s, {tN:.1f} °C", "mid" if windy else "ok", "Windy" if windy else "Normal"))
    else:
        factors.append(("Weather", "NASA POWER is not reachable right now", "the call uses the fire data only", "na", "No data"))
    lv = 3 if score >= 7 else 2 if score >= 5 else 1 if score >= 2 else 0
    return dict(level=lv, name=LEVELS[lv][0], advice=LEVELS[lv][1], score=score, sensor=sensor, n=n,
                by_sensor=by_sensor, newest=p.time_utc.max() if len(p) else None, factors=factors,
                areas=flagged, cells=cells, month=m)


def drift(points, A=None, month=None):
    """Live VIIRS / MODIS ratio against the p10-p90 band of past days of this month (2012 on), or None."""
    A = A or load_baseline()
    p = last_24h(points)
    b = p.sensor.value_counts()
    v = int(b.get("VIIRS_NOAA20", 0) or b.get("VIIRS_NOAA21", 0))
    mo = int(b.get("MODIS", 0))
    band = A["ratio"].get(str(month or dt.datetime.now(dt.timezone.utc).month))
    r = v / mo if mo else None
    ok = bool(band) and mo >= 20
    return dict(ratio=r, viirs=v, modis=mo, band=band, checked=ok,
                in_band=ok and band[0] <= r <= band[2])
