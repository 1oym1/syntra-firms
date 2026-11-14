"""SYNTRA fire calendar web app (Streamlit).

Run from the repo root:
    streamlit run app/app.py

Data: syntra.pipeline (FIRMS yearly files 2000-2025 + 2026 from the FIRMS API, cleaned by syntra.clean).
Harmonization: syntra.harmonize (fire-active 0.1 degree cell-days per month, MODIS -> VIIRS monthly factors),
extended to 2026 by syntra.series. Calendar: syntra.fire_calendar.
2026 needs FIRMS_MAP_KEY in .env (local) or in Streamlit secrets (deployed).
"""
import os
import pathlib
import sys

import folium
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from syntra import fire_calendar as fc  # noqa: E402
from syntra import harmonize as hz  # noqa: E402
from syntra import series  # noqa: E402
from syntra.data import DEFAULT_COUNTRY  # noqa: E402
from syntra.pipeline import load_country  # noqa: E402

COUNTRIES = ["Sudan", "Ethiopia", "Iraq", "Saudi_Arabia", "Australia", "Zambia", "South_Sudan", "Mexico"]
COLORS = {"MODIS": "#E69F00", "VIIRS_SNPP": "#56B4E9", "VIIRS_NOAA20": "#CC79A7", "harmonized": "#009E73",
          "Static source": "#D55E00"}  # Okabe-Ito, colorblind-safe
SENSOR = {"Terra": "MODIS", "Aqua": "MODIS", "N": "VIIRS_SNPP", "N20": "VIIRS_NOAA20"}
SENSOR_LABEL = {"MODIS": "MODIS", "VIIRS_SNPP": "VIIRS S-NPP", "VIIRS_NOAA20": "VIIRS NOAA-20"}
UNIT = "fire cell-days"
RAMPS = {"Inferno": px.colors.sequential.Inferno, "Cividis": px.colors.sequential.Cividis,
         "Viridis": px.colors.sequential.Viridis}
MAP_COLS = ["latitude", "longitude", "acq_date", "acq_time", "satellite", "frp", "daynight", "type"]

st.set_page_config(page_title="SYNTRA fire calendar", page_icon="🔥", layout="wide")

# Look: dark theme in .streamlit/config.toml; cards below. Data colors stay Okabe-Ito (colorblind-safe).
st.markdown("""<style>
.block-container {padding-top: 1.4rem;}
.hero {position: relative; overflow: hidden; border-radius: 18px; padding: 22px 26px 16px; margin-bottom: 14px;
  background: radial-gradient(900px 260px at 0% -30%, rgba(242,140,40,.38), transparent 62%),
              radial-gradient(700px 240px at 100% 130%, rgba(86,180,233,.22), transparent 60%),
              linear-gradient(135deg, #1a2338 0%, #0d1424 100%);
  border: 1px solid rgba(255,255,255,.09);}
.hero .eyebrow {font-size: .74rem; letter-spacing: .09em; text-transform: uppercase; color: #F2A65A; font-weight: 600;}
.hero h1 {font-size: 2.05rem; line-height: 1.15; margin: .25rem 0 .3rem; padding: 0; color: #fff;}
.hero p {color: #c9d1e0; margin: 0 0 .8rem; font-size: .98rem;}
.pill {display: inline-block; padding: 3px 11px; border-radius: 999px; margin: 0 6px 6px 0; font-size: .8rem;
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.13); color: #E6EAF2;}
.pill.live::before {content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: #3ddc84; margin-right: 6px; vertical-align: 1px; animation: pulse 1.8s infinite;}
@keyframes pulse {0% {box-shadow: 0 0 0 0 rgba(61,220,132,.7);} 70% {box-shadow: 0 0 0 7px rgba(61,220,132,0);}
  100% {box-shadow: 0 0 0 0 rgba(61,220,132,0);}}
.card {background: rgba(127,127,127,.09); border: 1px solid rgba(127,127,127,.18); border-radius: 14px;
  padding: 16px 20px; height: 100%;}
.status {border-left: 6px solid var(--c);}
.badge {display: inline-block; font-weight: 700; letter-spacing: .07em; font-size: .78rem; padding: 3px 10px;
  border-radius: 6px; border: 1px solid var(--c);}
.headline {font-size: 1.3rem; line-height: 1.35; margin: .55rem 0 .25rem;}
.sub {opacity: .75; font-size: .88rem;}
.card h4 {margin: 0 0 .4rem; padding: 0; font-size: .8rem; letter-spacing: .08em; text-transform: uppercase; opacity: .75;}
.big {font-size: 1.6rem; font-weight: 700;}
[data-testid="stMetric"] {background: rgba(127,127,127,.09); border: 1px solid rgba(127,127,127,.18);
  border-radius: 14px; padding: 12px 16px;}
[data-testid="stMetricLabel"] p {font-size: .82rem; opacity: .85;}
</style>""", unsafe_allow_html=True)


# ---------- data ----------
try:  # deployed: key in Streamlit secrets; local: .env (read by syntra.nrt)
    if "FIRMS_MAP_KEY" in st.secrets:
        os.environ.setdefault("FIRMS_MAP_KEY", st.secrets["FIRMS_MAP_KEY"])
except Exception:  # noqa: BLE001  (no secrets file)
    pass


@st.cache_resource(show_spinner=False, ttl=6 * 3600)
def get_country(country):
    """Clean fires (shared, read-only: cache_resource does not copy millions of rows on every rerun)."""
    return load_country(country)


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def get_series(country):
    d = get_country(country)
    return series.country_series(d["veg"], d["info"])


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def get_n20_check(country):
    d = get_country(country)
    return series.validate_n20(d["veg"], d["info"]["snpp_end"])


def in_box(df, bbox):
    if bbox is None:
        return df
    return df[df.longitude.between(bbox[0], bbox[2]) & df.latitude.between(bbox[1], bbox[3])]


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def analyse(country, bbox):
    """(monthly table, this-month-so-far) for the whole country or a box inside it."""
    d = get_country(country)
    cs = get_series(country)
    if bbox is None:
        return cs["tab"], series.month_to_date(d["veg"], d["info"])
    area = in_box(d["veg"], bbox)
    return series.area_series(area, d["info"], cs), series.month_to_date(area, d["info"])


BANDS = {("latitude", 1): ["All"], ("longitude", 1): ["All"], ("latitude", 2): ["North", "South"], ("latitude", 3): ["North", "Central", "South"],
         ("longitude", 2): ["West", "East"], ("longitude", 3): ["West", "Central", "East"]}


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def regions_over_time(country, bbox, coord, n, step):
    """Harmonized fire cell-days per week (or month) for n equal-width bands of the area.

    Same rules as the monthly series: VIIRS S-NPP from 2012 (NOAA-20 x k after S-NPP's last day),
    MODIS x the country's monthly MODIS->VIIRS factor before (x the Terra factor before Aqua, Jul 2002)."""
    d, cs = get_country(country), get_series(country)
    info, v = d["info"], in_box(d["veg"], bbox)
    lo, hi = float(v[coord].min()), float(v[coord].max())
    edges = np.linspace(lo, hi, n + 1)
    band = np.clip(np.digitize(v[coord].values, edges[1:-1]), 0, n - 1)
    if coord == "latitude":
        band = n - 1 - band                       # first band = north
    v = v.assign(band=band)

    def daily(rows):
        return rows.drop_duplicates(["band", "acq_date", "cell_id"]).groupby(["acq_date", "band"]).size()

    days = pd.date_range("2000-11-01", info["complete_day"], freq="D")
    full = pd.MultiIndex.from_product([days, range(n)], names=["acq_date", "band"])
    m = daily(v[v.family == "MODIS"]).reindex(full, fill_value=0).unstack()
    sn = daily(v[v.satellite == "N"]).reindex(full, fill_value=0).unstack()
    n20 = daily(v[v.satellite == "N20"]).reindex(full, fill_value=0).unstack()
    mon = m.index.month.values - 1
    kv = cs["k_viirs"].reindex(range(1, 13)).values[mon]
    kt = np.where(m.index < pd.Timestamp("2002-07-01"), cs["k_terra"].reindex(range(1, 13)).values[mon], 1.0)
    out = m.mul(kv * kt, axis=0)
    viirs = m.index >= series.VIIRS_START.to_timestamp()   # first full S-NPP month (data from 20 Jan 2012)
    out[viirs] = sn[viirs]
    end, k = info.get("snpp_end"), info.get("k_n20")
    if end is not None and k is not None and np.isfinite(k):
        after = m.index > end
        out[after] = n20[after] * k
    if step == "Week":
        out = out.resample("W-MON", label="left", closed="left").sum()
    elif step == "Month":
        out = out.resample("MS").sum()
    out.columns = BANDS[(coord, n)]
    return out, edges


def column(tab, col):
    """Monthly Series (PeriodIndex); months a sensor did not fly are NaN, not 0."""
    s = series.as_series(tab, col)
    flying = {"modis_cells": "modis_flying", "viirs_cells": "viirs_flying"}.get(col)
    if flying:
        s[~tab[flying].values] = np.nan
    return s


def bbox_from_drawing(drawing):
    if not drawing or "geometry" not in drawing:
        return None
    pts = np.array(drawing["geometry"]["coordinates"][0])  # [[lon, lat], ...]
    return (round(pts[:, 0].min(), 3), round(pts[:, 1].min(), 3),
            round(pts[:, 0].max(), 3), round(pts[:, 1].max(), 3))


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def level(c):
    """Plain-language status of a month vs the same month in earlier years: (label, icon, color).
    Icon + word + color, so it never relies on color alone."""
    a = c["anomaly_pct"]
    if not np.isfinite(a):
        return "No baseline yet", "⚪", "#999999"
    if np.isfinite(c["p90"]) and c["value"] > c["p90"]:
        return "Very high", "🔴", "#D55E00"
    if a >= 20:
        return "Above normal", "🟠", "#E69F00"
    if a <= -20:
        return "Below normal", "🔵", "#56B4E9"
    return "Normal", "🟢", "#009E73"


def year_to_date(s, month):
    """Jan..month total of `month`'s year and the median of the same months in earlier complete years."""
    cal = fc.calendar(s).iloc[:, :month.month]
    full = cal.dropna()
    cur = float(cal.loc[month.year].sum()) if month.year in cal.index else float("nan")
    past = full[full.index < month.year].sum(axis=1)
    return cur, float(past.median()) if len(past) else float("nan"), len(past)


def annual_totals(s):
    """Totals of full years only (12 months of data)."""
    cal = fc.calendar(s).dropna()
    return cal.sum(axis=1)


def linear_trend(y):
    """OLS slope per year, in % of the mean per decade, and the fit's R2 (for orientation only)."""
    x = y.index.values.astype(float)
    b, a = np.polyfit(x, y.values, 1)
    fit = a + b * x
    r2 = 1 - ((y.values - fit) ** 2).sum() / ((y.values - y.values.mean()) ** 2).sum()
    return b, 100 * 10 * b / y.mean(), r2, pd.Series(fit, index=y.index)


def report_html(title, blocks, figs):
    """One HTML file: the summary text and the interactive charts (FR16)."""
    parts = [f"<html><head><meta charset='utf-8'><title>{title}</title><style>body{{font-family:sans-serif;"
             "max-width:1100px;margin:24px auto;padding:0 16px;color:#1b2333}h1{margin-bottom:4px}"
             ".muted{color:#667}</style></head><body>", f"<h1>{title}</h1>"]
    parts += blocks
    for i, (name, f) in enumerate(figs.items()):
        parts.append(f"<h2>{name}</h2>" + f.to_html(full_html=False, include_plotlyjs="cdn" if i == 0 else False))
    parts.append("<p class='muted'>SYNTRA · NASA Space Apps 2026 · data: NASA FIRMS (MODIS C6.1, VIIRS 375 m).</p>"
                 "</body></html>")
    return "\n".join(parts).encode()


# ---------- sidebar ----------
with st.sidebar:
    st.title("🔥 SYNTRA fire calendar")
    st.caption("MODIS + VIIRS hotspots harmonized into one record · NASA Space Apps 2026, Jeddah")
    country = st.selectbox("Country", COUNTRIES, index=COUNTRIES.index(DEFAULT_COUNTRY) if DEFAULT_COUNTRY in COUNTRIES else 0,
                           format_func=lambda c: c.replace("_", " "))
    other = st.text_input("…or another FIRMS country name", placeholder="e.g. Kazakhstan")
    country = other.strip().replace(" ", "_") or country

with st.spinner(f"Loading {country.replace('_', ' ')} from NASA FIRMS (first time takes a few minutes)…"):
    try:
        data = get_country(country)
        veg, info = data["veg"], data["info"]
        cs = get_series(country) if len(veg) else None
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not load '{country}': {e}")
        st.stop()
if cs is None:
    st.error(f"No FIRMS data for '{country}'. Check the spelling (FIRMS uses underscores).")
    st.stop()

with st.sidebar:
    st.subheader("Area of interest")
    mode = st.radio("Area", ["Whole country", "Draw on map", "Type lat/lon"], label_visibility="collapsed")
    bbox = None
    if mode == "Type lat/lon":
        c1, c2 = st.columns(2)
        w = c1.number_input("West", value=float(round(veg.longitude.min(), 2)), step=0.5)
        e = c2.number_input("East", value=float(round(veg.longitude.max(), 2)), step=0.5)
        s = c1.number_input("South", value=float(round(veg.latitude.min(), 2)), step=0.5)
        n = c2.number_input("North", value=float(round(veg.latitude.max(), 2)), step=0.5)
        bbox = (w, s, e, n)

if mode == "Draw on map":
    st.markdown("**Draw a rectangle** with the ■ tool on the left of the map, then the page updates.")
    m = folium.Map(location=[veg.latitude.median(), veg.longitude.median()], zoom_start=5, tiles="OpenStreetMap")
    Draw(draw_options={"rectangle": True, "polygon": False, "polyline": False, "circle": False,
                       "marker": False, "circlemarker": False}, edit_options={"edit": False}).add_to(m)
    drawn = st_folium(m, height=380, use_container_width=True, returned_objects=["last_active_drawing"])
    bbox = bbox_from_drawing((drawn or {}).get("last_active_drawing"))
    if bbox is None:
        st.info("No rectangle yet: showing the whole country.")

h, mtd = analyse(country, bbox)
if h is None or np.nansum(h["harmonized_cells"]) == 0:
    st.warning("No vegetation fires in this area. Draw a bigger box.")
    st.stop()
harm = column(h, "harmonized_cells")

with st.sidebar:
    months = list(harm.dropna().index[::-1])
    sel = st.selectbox("Month to compare", months, format_func=lambda p: p.strftime("%B %Y"))
    view = st.radio("Calendar shows", ["Harmonized", "Raw MODIS", "Raw VIIRS"])
    ramp = st.selectbox("Color ramp (colorblind-safe)", ["Inferno", "Cividis", "Viridis"])
    st.caption(f"Data through **{info['complete_day']:%d %b %Y}**; the calendar runs to the last complete month. "
               + ("2026 from the FIRMS API (near-real-time, provisional)." if info.get("key")
                  else "No FIRMS_MAP_KEY set: archive only (to Dec 2025)."))

shown = column(h, {"Harmonized": "harmonized_cells", "Raw MODIS": "modis_cells", "Raw VIIRS": "viirs_cells"}[view])
cmp = fc.month_vs_median(harm, sel)
ho = cs["heldout"]

# ---------- hero + status ----------
place = country.replace("_", " ") + ("" if bbox is None else f" · box W{bbox[0]} S{bbox[1]} E{bbox[2]} N{bbox[3]}")
live = (f'<span class="pill live">Live · FIRMS data through {info["complete_day"]:%d %b %Y}</span>' if info.get("key")
        else f'<span class="pill">Archive · data through {info["complete_day"]:%d %b %Y}</span>')
st.markdown(f"""<div class="hero">
<div class="eyebrow">NASA Space Apps 2026 · Harmonization of MODIS and VIIRS hot spots</div>
<h1>Burning activity: {place}</h1>
<p>One consistent record of vegetation fires from 2000 to today, whichever satellite saw them.</p>
{live}<span class="pill">MODIS Terra + Aqua · VIIRS S-NPP + NOAA-20</span>
<span class="pill">Harmonization R² {ho['r2']:.2f} on held-out years (raw MODIS {ho['r2_raw_modis']:.2f})</span>
</div>""", unsafe_allow_html=True)

lab, icon, col = level(cmp)
mon = sel.strftime("%B")
nth = f"{ordinal(cmp['rank'])} highest of {cmp['n_years'] + 1} {mon}s since 2000" if cmp["rank"] else ""
if np.isfinite(cmp["anomaly_pct"]):
    word = "above" if cmp["anomaly_pct"] >= 0 else "below"
    head = (f"{sel.strftime('%B %Y')}: <b>{cmp['value']:,.0f}</b> fire cell-days, "
            f"<b>{abs(cmp['anomaly_pct']):.0f}% {word}</b> a typical {mon}")
else:
    head = f"{sel.strftime('%B %Y')}: <b>{cmp['value']:,.0f}</b> fire cell-days"
nxt = sel + 1
nh = harm[(harm.index.month == nxt.month) & (harm.index < nxt)].dropna()
s1, s2 = st.columns([2, 1])
s1.markdown(f"""<div class="card status" style="--c:{col}">
<span class="badge">{icon} {lab.upper()}</span>
<div class="headline">{head}</div>
<div class="sub">{nth} · median {cmp['median']:,.0f} · 90th percentile {cmp['p90']:,.0f}</div>
</div>""", unsafe_allow_html=True)
if len(nh):
    so_far = ""
    if mtd is not None and info["complete_day"].to_period("M") == nxt and np.isfinite(mtd["anomaly_pct"]):
        so_far = (f"<div class='sub'>So far (1–{mtd['through_day']} {nxt.strftime('%b')}): "
                  f"{mtd['anomaly_pct']:+.0f}% vs the same days, {ordinal(mtd['rank'])} of {mtd['n_years'] + 1}</div>")
    s2.markdown(f"""<div class="card"><h4>What {nxt.strftime('%B')} usually brings</h4>
<div class="big">{nh.median():,.0f}</div>
<div class="sub">typical range {nh.quantile(.1):,.0f}–{nh.quantile(.9):,.0f} ({len(nh)} years).
Climatology, not a forecast.</div>{so_far}</div>""", unsafe_allow_html=True)

st.write("")
ytd, ytd_med, ytd_n = year_to_date(harm, sel)
rec = harm.dropna()
k1, k2, k3, k4 = st.columns(4)
k1.metric(sel.strftime("%b %Y"), f"{cmp['value']:,.0f}",
          f"{cmp['anomaly_pct']:+.0f}% vs median" if np.isfinite(cmp["anomaly_pct"]) else None,
          delta_color="inverse", help="Fire cell-days in the month, VIIRS S-NPP units")
k2.metric(f"Jan–{sel.strftime('%b')} {sel.year} total", f"{ytd:,.0f}",
          f"{100 * (ytd / ytd_med - 1):+.0f}% vs median of {ytd_n} years" if ytd_med > 0 else None,
          delta_color="inverse")
k3.metric(f"Busiest month on record: {rec.idxmax().strftime('%b %Y')}", f"{rec.max():,.0f}")
top = fc.busiest_years(harm)
k4.metric(f"Busiest full year: {top.index[0]}" if len(top) else "Busiest full year",
          f"{top.iloc[0]:,.0f}" if len(top) else "n/a")
with st.expander("What is a fire cell-day?"):
    st.markdown("Each day, the map is cut into 0.1° squares (about 11 km). A square with at least one vegetation-fire "
                "detection that day counts 1. A month's value is the sum over its days. One fire counts once per "
                "day for both sensors, so the number measures how much burning there was, not how many pixels saw "
                "it. Values are in VIIRS S-NPP units: older MODIS months are converted with monthly factors fitted "
                "on 2012–2021, when both sensors flew. Source: NASA FIRMS.")

if mtd is not None and np.isfinite(mtd["value"]):
    day = info["complete_day"]
    st.subheader(f"This month so far: {day:%B} 1–{mtd['through_day']}, {day.year}")
    m1, m2, m3 = st.columns(3)
    m1.metric(f"{day:%b} 1–{mtd['through_day']}, {day.year}", f"{mtd['value']:,.0f}",
              f"{mtd['anomaly_pct']:+.0f}% vs median" if np.isfinite(mtd["anomaly_pct"]) else None,
              delta_color="inverse")
    m2.metric(f"Median of the same days ({mtd['n_years']} years)", f"{mtd['median']:,.0f}")
    m3.metric("Rank among the same days", f"#{mtd['rank']} of {mtd['n_years'] + 1}")
    note = f"Same days of the month in every VIIRS year (2012 on), so a part month is compared fairly. "
    if info.get("snpp_end") is not None and day > info["snpp_end"]:
        note += (f"Suomi NPP data ends {info['snpp_end']:%d %b %Y}; this month uses VIIRS NOAA-20 × "
                 f"{info['k_n20']:.3f} (S-NPP-equivalent). ")
    st.caption(note + "Near-real-time data: provisional.")

figs = {}
tab_cal, tab_risk, tab_3d, tab_tr, tab_h, tab_map, tab_data, tab_m = st.tabs(
    ["📅 Burning calendar", "⚠️ Risk periods", "🧊 3D view", "📈 Trend & the 2012 jump", "🛰️ Harmonization", "🗺️ Hotspot map",
     "⬇️ Download", "📖 Method"])

# ---------- calendar ----------
with tab_cal:
    cal = fc.calendar(shown)
    fig = px.imshow(cal, color_continuous_scale=ramp, aspect="auto", text_auto=".0f",
                    labels=dict(x="Month", y="Year", color=UNIT))
    fig.update_traces(textfont_size=9)
    fig.update_yaxes(dtick=1, autorange="reversed")
    if view == "Harmonized":
        fig.add_hline(y=2011.5, line_dash="dash", line_color="white",
                      annotation_text="↑ MODIS converted to VIIRS-equivalent   ↓ VIIRS observed",
                      annotation_position="top left", annotation_font_color="white")
    if sel.year in cal.index:
        fig.add_shape(type="rect", x0=sel.month - 1.5, x1=sel.month - 0.5,
                      y0=sel.year - 0.5, y1=sel.year + 0.5, line=dict(color="cyan", width=3))
    fig.update_layout(height=40 + 26 * len(cal), margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig)
    figs[f"Burning calendar ({view.lower()})"] = fig

    c1, c2 = st.columns(2)
    with c1:
        same = harm[harm.index.month == sel.month].dropna()
        bar = go.Figure(go.Bar(x=same.index.year, y=same.values,
                               marker_color=[COLORS["harmonized"] if p == sel else "#8a94a6" for p in same.index]))
        bar.add_hline(y=cmp["median"], line_dash="dash", annotation_text="historical median")
        bar.update_layout(title=f"Every {mon} since 2000", height=360,
                          margin=dict(l=0, r=0, t=40, b=0), yaxis_title=UNIT)
        st.plotly_chart(bar)
        figs[f"Every {mon} since 2000"] = bar
    with c2:
        hist = harm[harm.index.year < sel.year]
        clim = fc.calendar(hist).median()
        this = fc.calendar(harm).loc[sel.year] if sel.year in fc.calendar(harm).index else None
        clock = go.Figure()
        clock.add_barpolar(r=clim.values, theta=fc.MONTHS, name="Typical year (median)",
                           marker_color="rgba(160,170,190,0.45)", marker_line_width=0)
        if this is not None:
            r = list(this.values) + [this.values[0]]
            clock.add_scatterpolar(r=r, theta=fc.MONTHS + [fc.MONTHS[0]], mode="lines+markers", name=str(sel.year),
                                   line=dict(color=COLORS["harmonized"], width=2), marker_size=8)
        clock.update_layout(title="Fire-season clock", height=360, margin=dict(l=30, r=30, t=40, b=10),
                            polar=dict(angularaxis=dict(direction="clockwise", rotation=90)),
                            legend=dict(orientation="h", y=-0.05))
        st.plotly_chart(clock)
        figs["Fire-season clock"] = clock
        if len(hist.dropna()):
            st.caption(f"Peak months (median): **{', '.join(fc.peak_months(fc.calendar(hist)))}** · busiest full "
                       "years: " + ", ".join(f"**{y}** ({v:,.0f})" for y, v in top.items()))
        src = h.loc[(h.year == sel.year) & (h.month == sel.month), "source"]
        if len(src):
            st.caption(f"Source of {sel.strftime('%b %Y')}: {src.iloc[0]}")

# ---------- risk periods ----------
with tab_risk:
    st.markdown("**When is fire risk highest?** The calendar shows when fires happened. This tab shows when burning has "
                "*usually* been intense and frequent, week by week of the year, from every year since 2001, and "
                "whether the fire season is starting earlier or lasting longer.")
    daily = regions_over_time(country, bbox, "latitude", 1, "Day")[0].iloc[:, 0]
    day0 = info["complete_day"]
    dd = daily[daily.index <= day0].to_frame("v")
    dd["year"], dd["doy"] = dd.index.year, dd.index.dayofyear
    dd["wk"] = np.minimum((dd.doy - 1) // 7, 51)
    g = dd.groupby(["year", "wk"]).v.agg(["sum", "count"])
    g = g[g["count"] >= 7]                                           # complete weeks only
    wk = (g["sum"] * 7 / g["count"]).unstack()                       # per 7 days (the last week has 8-9 days)
    full_years = [y for y in wk.index if 2001 <= y < day0.year]
    base = wk.loc[full_years]
    r1, r2 = st.columns([1, 1])
    q = r1.select_slider("A week counts as 'high activity' above this percentile of all weeks", [50, 60, 70, 75, 80, 90],
                         value=75)
    yr_from = r2.slider("Years used", int(min(full_years)), int(max(full_years)),
                        (int(min(full_years)), int(max(full_years))))
    base = base.loc[yr_from[0]:yr_from[1]]
    thr = float(np.nanpercentile(base.values, q))
    freq = 100 * (base >= thr).mean()
    med, p90 = base.median(), base.quantile(0.9)
    cls = pd.cut(freq, [-1, 25, 50, 75, 101], labels=["Low", "Moderate", "High", "Extreme"])
    RISK = {"Low": "#FEE391", "Moderate": "#FB9A29", "High": "#CC4C02", "Extreme": "#662506"}  # YlOrBr steps
    ref = pd.Timestamp("2001-01-01")
    lab = [(ref + pd.Timedelta(days=7 * w)).strftime("%d %b") for w in range(52)]

    # highest-risk periods: runs of consecutive weeks in the top class present
    order = ["Extreme", "High", "Moderate"]
    top_cls = next((c for c in order if (cls == c).any()), None)
    periods = []
    if top_cls:
        on = (cls == top_cls).values
        runs, start = [], None
        for w in range(52):
            if on[w] and start is None:
                start = w
            if (not on[w] or w == 51) and start is not None:
                runs.append([start, w if on[w] else w - 1]); start = None
        if len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == 51:   # wraps over New Year
            runs[0][0] = runs[-1][0] - 52; runs.pop()
        for a, b in sorted(runs, key=lambda r: -freq.iloc[[w % 52 for w in range(r[0], r[1] + 1)]].mean()):
            ws = [w % 52 for w in range(a, b + 1)]
            end = ref + pd.Timedelta(days=7 * (b % 52) + 6)
            periods.append(f"**{lab[a % 52]} – {end:%d %b}**: high activity in "
                           f"{freq.iloc[ws].mean():.0f}% of years, typically {med.iloc[ws].mean():,.0f} fire cell-days "
                           f"a week ({p90.iloc[ws].mean():,.0f} in a bad year)")
    a1, a2 = st.columns([1, 2])
    a1.markdown(f"<div class='card status' style='--c:{RISK.get(top_cls, '#999')}'><h4>Highest-risk period"
                f"{'s' if len(periods) > 1 else ''}</h4><span class='badge'>{(top_cls or 'n/a').upper()}</span>"
                f"<div class='sub' style='margin-top:.5rem'>Weeks where at least "
                f"{ {'Extreme': 75, 'High': 50, 'Moderate': 25}.get(top_cls, 0)}% of years ({yr_from[0]}–{yr_from[1]}) "
                f"had high activity (above {thr:,.0f} fire cell-days a week, the {q}th percentile).</div></div>",
                unsafe_allow_html=True)
    a2.markdown("\n".join(f"- {p}" for p in periods[:3]) or "No week reaches the moderate class.")

    rb = go.Figure(go.Bar(x=lab, y=freq.values, marker_color=[RISK[c] for c in cls.astype(str)],
                          customdata=np.c_[med.values, p90.values, cls.astype(str)],
                          hovertemplate="Week of %{x}<br>High activity in <b>%{y:.0f}%</b> of years · %{customdata[2]}"
                                        "<br>Typical %{customdata[0]:,.0f} · bad year %{customdata[1]:,.0f} "
                                        "fire cell-days<extra></extra>"))
    for name, y in (("Extreme", 75), ("High", 50), ("Moderate", 25)):
        rb.add_hline(y=y, line_dash="dot", line_color="rgba(160,170,190,0.5)", annotation_text=name,
                     annotation_position="right")
    rb.update_layout(title="How often each week of the year has high fire activity", height=360,
                     yaxis=dict(title="% of years", range=[0, 105]), xaxis=dict(title="", tickangle=-45, dtick=4),
                     margin=dict(l=0, r=40, t=40, b=0), bargap=0.15)
    st.plotly_chart(rb)
    figs["Fire risk by week of the year"] = rb

    # years x weeks: where each week ranks in the whole record (0-100)
    pct = wk.stack().rank(pct=True).mul(100).unstack().reindex(columns=range(52))
    hm = px.imshow(pct, color_continuous_scale="YlOrBr", aspect="auto", zmin=0, zmax=100,
                   labels=dict(x="Week of the year", y="Year", color="percentile"))
    hm.update_xaxes(tickvals=list(range(0, 52, 4)), ticktext=lab[::4])
    hm.update_yaxes(dtick=1, autorange="reversed")
    hm.update_traces(hovertemplate="%{y}, week of " + "%{x}<br>busier than %{z:.0f}% of all weeks<extra></extra>")
    hm.update_layout(title="Every week since 2001, ranked against the whole record", height=40 + 22 * len(pct),
                     margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(hm)
    figs["Weekly risk ranking"] = hm

    # season start, end and length per fire year (a fire year starts at the quietest week, so a season
    # that crosses New Year stays in one piece)
    origin = int(med.values.argmin())
    rows = []
    for y in wk.index:
        seq = pd.concat([wk.loc[y].iloc[origin:], wk.loc[y + 1].iloc[:origin] if y + 1 in wk.index
                         else pd.Series(np.nan, index=range(origin))]) if origin else wk.loc[y]
        seq = pd.Series(seq.values)
        if seq.isna().any():
            continue
        hi_w = np.where(seq.values >= thr)[0]
        if len(hi_w):
            rows.append({"fire year": f"{y}/{str(y + 1)[2:]}" if origin else str(y), "y": y,
                         "start": int(hi_w[0]), "end": int(hi_w[-1]), "high weeks": len(hi_w)})
    if len(rows) >= 5:
        sz = pd.DataFrame(rows)

        def wlab(i):
            return (ref + pd.Timedelta(days=7 * ((i + origin) % 52))).strftime("%d %b")

        sf = go.Figure()
        sf.add_bar(x=sz["fire year"], y=sz.end - sz.start + 1, base=sz.start, marker_color="#CC4C02",
                   customdata=np.c_[[wlab(i) for i in sz.start], [wlab(i) for i in sz.end], sz["high weeks"]],
                   hovertemplate="%{x}: first high week %{customdata[0]}, last %{customdata[1]}<br>"
                                 "%{customdata[2]} high weeks<extra></extra>", name="Season (first to last high week)")
        ticks = list(range(0, 52, 4))
        sf.update_layout(title="Fire season each year: first to last high-activity week", height=380,
                         yaxis=dict(title="", tickvals=ticks, ticktext=[wlab(i) for i in ticks], autorange="reversed"),
                         margin=dict(l=0, r=0, t=40, b=0), showlegend=False)
        st.plotly_chart(sf)
        figs["Fire season length"] = sf
        b_len, _ = np.polyfit(sz.y, sz["high weeks"], 1)
        b_start, _ = np.polyfit(sz.y, sz.start, 1)
        st.caption(f"Across {len(sz)} fire years: the number of high-activity weeks changes by {10 * b_len:+.1f} weeks "
                   f"per decade, and the first high week moves {abs(7 * 10 * b_start):.0f} days per decade "
                   f"{'earlier' if b_start < 0 else 'later'} (linear fits; years vary, so read these as directions). "
                   + (f"Fire years start in the quietest week ({wlab(0)}), so a season that crosses New Year stays "
                      "in one piece." if origin else ""))
    st.caption("All values are harmonized fire cell-days (VIIRS units) per 7 days. Change the percentile and years "
               "above to make 'high activity' stricter or looser.")

# ---------- trend + 2012 jump ----------
with tab_tr:
    ann = annual_totals(harm)
    naive = pd.concat([annual_totals(column(h, "modis_cells")).loc[lambda s: s.index < 2012],
                       annual_totals(column(h, "viirs_cells")).loc[lambda s: s.index >= 2012]])

    def jump(s):
        a, b = s.loc[2009:2011], s.loc[2012:2014]
        return b.mean() / a.mean() if len(a) and len(b) and a.mean() > 0 else float("nan")

    j_raw, j_h = jump(naive), jump(ann)
    st.markdown(f"**The 2012 jump, removed.** Plotting raw counts (MODIS until 2011, VIIRS after) makes burning look "
                f"like it jumped **×{j_raw:.1f}** in 2012, only because VIIRS started. After harmonization the "
                f"step is **×{j_h:.2f}**: the change reflects fires, not satellites.")
    jf = go.Figure()
    jf.add_scatter(x=naive.index, y=naive.values, name="Raw: MODIS to 2011, then VIIRS", mode="lines+markers",
                   line=dict(color="#8a94a6", dash="dot"))
    jf.add_scatter(x=ann.index, y=ann.values, name="Harmonized (one record)", mode="lines+markers",
                   line=dict(color=COLORS["harmonized"], width=3))
    jf.add_vline(x=2011.5, line_dash="dash", line_color=COLORS["VIIRS_SNPP"],
                 annotation_text="VIIRS starts (2012)", annotation_position="top left")
    jf.update_layout(height=380, margin=dict(l=0, r=0, t=30, b=0), yaxis_title=f"{UNIT} / year",
                     legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(jf)
    figs["The 2012 jump, removed"] = jf

    if len(ann) >= 5:
        b, pct, r2t, fit = linear_trend(ann)
        tf = go.Figure()
        tf.add_bar(x=ann.index, y=ann.values, name="Harmonized total per year", marker_color=COLORS["harmonized"])
        tf.add_scatter(x=fit.index, y=fit.values, name=f"Linear trend ({pct:+.0f}% per decade)",
                       line=dict(color="#F0E442", dash="dash", width=2))
        tf.update_layout(height=340, margin=dict(l=0, r=0, t=30, b=0), yaxis_title=f"{UNIT} / year",
                         legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(tf)
        figs["Long-term trend"] = tf
        st.caption(f"Full years {ann.index.min()}–{ann.index.max()}. Linear fit: {b:+,.0f} {UNIT} per year "
                   f"({pct:+.0f}% of the mean per decade), fit R² {r2t:.2f}. Years vary a lot, so read the trend "
                   "as a direction, not a prediction.")

# ---------- harmonization ----------
with tab_h:
    st.markdown("**Why harmonize?** VIIRS (375 m) sees many more and smaller fires than MODIS (1 km). "
                "Plotted raw, the record seems to jump in 2012 when VIIRS starts. "
                "After harmonization the sensor of origin no longer matters.")
    if bbox is not None:
        st.caption("The factors and the validation below are fitted on the whole country; the box reuses them "
                   "(a small area has too few fires to fit its own).")
    t = harm.index.to_timestamp()
    ts = go.Figure()
    ts.add_scatter(x=t, y=column(h, "modis_cells"), name="Raw MODIS", line_color=COLORS["MODIS"])
    ts.add_scatter(x=t, y=column(h, "viirs_cells"), name="Raw VIIRS (S-NPP)", line_color=COLORS["VIIRS_SNPP"])
    ts.add_scatter(x=t, y=series.as_series(h, "modis_as_viirs"), name="MODIS converted to VIIRS-equivalent",
                   line=dict(color=COLORS["harmonized"], dash="dot"))
    ts.update_layout(height=380, margin=dict(l=0, r=0, t=30, b=0), yaxis_title=f"{UNIT} / month",
                     legend=dict(orientation="h"))
    st.plotly_chart(ts)
    figs["Raw MODIS, raw VIIRS and MODIS converted"] = ts

    val = cs["validation"]
    c1, c2 = st.columns(2)
    with c1:
        p = ho["predictions"]
        sc = go.Figure()
        sc.add_scatter(x=p["viirs_cells"], y=p["modis_consistent"], mode="markers", name="Raw MODIS",
                       marker_color=COLORS["MODIS"], opacity=0.6)
        sc.add_scatter(x=p["viirs_cells"], y=p["pred"], mode="markers", name="Harmonized (held-out year)",
                       marker_color=COLORS["harmonized"], opacity=0.7)
        mx = float(p["viirs_cells"].max())
        sc.add_scatter(x=[0, mx], y=[0, mx], mode="lines", name="perfect agreement",
                       line=dict(color="gray", dash="dash"))
        sc.update_layout(title="Predicted vs observed VIIRS, leave-one-year-out", height=420,
                         xaxis_title="observed VIIRS", yaxis_title="estimate",
                         margin=dict(l=0, r=0, t=40, b=0), legend=dict(orientation="h", y=-0.18, yanchor="top"))
        st.plotly_chart(sc)
        figs["Validation: predicted vs observed"] = sc
    with c2:
        st.markdown(f"**Validation**: {ho['n_months']} months, {hz.OVERLAP[0]}–{hz.OVERLAP[1]}, each year "
                    f"predicted from MODIS by factors fitted on the other years. Monthly R² **{ho['r2']:.3f}** "
                    f"(raw MODIS {ho['r2_raw_modis']:.3f}).")
        if len(val):
            st.markdown(f"Median annual error **{val['annual_error_%'].abs().median():.1f}%** · median monthly "
                        f"error (MAPE) **{val['monthly_MAPE_%'].median():.1f}%** · median monthly r "
                        f"**{val['monthly_r'].median():.3f}**")
            st.dataframe(val.set_index("year"), height=250)
        vn = get_n20_check(country)
        if vn:
            st.markdown(f"**NOAA-20 → S-NPP (after S-NPP data ends):** k = {vn['k']:.3f}; {vn['n_months']} months "
                        f"both flew, held-out R² {vn['r2']:.3f}, bias {vn['bias_pct']:+.1f} %.")
    fac = pd.DataFrame({"month": fc.MONTHS, "Terra → Terra+Aqua (2000–02)": cs["k_terra"].values,
                        "MODIS → VIIRS": cs["k_viirs"].values})
    fb = px.bar(fac.melt("month", var_name="factor", value_name="×"), x="month", y="×", color="factor",
                barmode="group", color_discrete_sequence=[COLORS["MODIS"], COLORS["VIIRS_SNPP"]])
    fb.update_layout(title=f"Monthly factors (annual: Terra {cs['k_terra_all']:.2f}, MODIS→VIIRS "
                           f"{cs['k_viirs_all']:.2f})", height=280, margin=dict(l=0, r=0, t=40, b=0),
                     legend=dict(orientation="h", title=None))
    st.plotly_chart(fb)

# ---------- hotspot map ----------
with tab_map:
    pts_all = in_box(veg, bbox)
    last = info["complete_day"].date()
    d0 = sel.to_timestamp().date()
    d1 = min((sel + 1).to_timestamp().date() - pd.Timedelta(days=1), last)
    c1, c2, c3 = st.columns([1.3, 1.5, 1.2])
    when = c1.segmented_control("View", ["Live: last 7 days", f"{sel.strftime('%b %Y')}", "Custom dates"],
                                default=f"{sel.strftime('%b %Y')}") or f"{sel.strftime('%b %Y')}"
    picked = c2.pills("Sensors (tap to turn on/off)", list(SENSOR_LABEL.values()), selection_mode="multi",
                      default=list(SENSOR_LABEL.values()))
    show_static = c3.toggle("Static sources (gas flares, industry)", value=False,
                            help="Always-hot places removed by cleaning. Turn on to see what was filtered out.")
    density = c3.toggle("Density view", value=False, help="Heat map of where fires cluster, instead of points.")
    if when.startswith("Live"):
        rng = (last - pd.Timedelta(days=6), last)
    elif when == "Custom dates":
        rng = st.date_input("Date range", (d0, d1), min_value=veg.acq_date.min().date(), max_value=last)
    else:
        rng = (d0, d1)
    keep = [k for k, v in SENSOR_LABEL.items() if v in (picked or [])]
    pts = pts_all.iloc[0:0].assign(sensor=pd.Series(dtype=str))
    if isinstance(rng, (tuple, list)) and len(rng) == 2:
        pts = pts_all[pts_all.acq_date.between(pd.Timestamp(rng[0]), pd.Timestamp(rng[1]))]
        pts = pts.assign(sensor=pts.satellite.map(SENSOR))
        pts = pts[pts.sensor.isin(keep)]
        if when.startswith("Live") and not info.get("key"):
            st.caption("No FIRMS_MAP_KEY: \"live\" shows the last 7 days of the archive.")
        n = pts.sensor.value_counts()
        snpp_end = info.get("snpp_end")
        if "VIIRS_SNPP" in keep and snpp_end is not None and pd.Timestamp(rng[1]) > snpp_end:
            st.caption(f"Suomi NPP data ends {snpp_end:%d %b %Y}; after that VIIRS comes from NOAA-20.")
        st.caption(f"**{rng[0]:%d %b %Y} → {rng[1]:%d %b %Y}** · {len(pts):,} vegetation-fire hotspots ("
                   + ", ".join(f"{n.get(k, 0):,} {SENSOR_LABEL[k]}" for k in keep) + "). "
                   "Calendar and anomalies use vegetation fires only.")
        show = pts.sample(30000, random_state=0) if len(pts) > 30000 else pts
        show = show[["sensor", "acq_date", "latitude", "longitude", "frp"]]
        if show_static:
            stc = in_box(data["static"], bbox)
            stc = stc[stc.acq_date.between(pd.Timestamp(rng[0]), pd.Timestamp(rng[1]))]
            stc = stc[stc.satellite.map(SENSOR).isin(keep)] if "satellite" in stc else stc
            st.caption(f"Plus {len(stc):,} static-source hotspots (red): always-hot sites removed by cleaning, "
                       "not counted as fires.")
            show = pd.concat([show, stc.assign(sensor="Static source")[show.columns]], ignore_index=True)
        if len(show):
            centre = dict(lat=float(pts_all.latitude.median()), lon=float(pts_all.longitude.median()))
            if density:
                mp = px.density_map(show[show.sensor != "Static source"], lat="latitude", lon="longitude",
                                    radius=7, center=centre, zoom=4.3, height=560, map_style="carto-darkmatter",
                                    color_continuous_scale="Inferno")
                mp.update_coloraxes(showscale=False)
                stx = show[show.sensor == "Static source"]
                if len(stx):
                    mp.add_scattermap(lat=stx.latitude, lon=stx.longitude, mode="markers", name="Static source",
                                      marker=dict(color=COLORS["Static source"], size=7))
            else:
                mp = px.scatter_map(show, lat="latitude", lon="longitude", color="sensor",
                                    hover_data=["acq_date", "frp"], color_discrete_map=COLORS, height=560,
                                    map_style="carto-darkmatter", center=centre, zoom=4.3,
                                    labels={"sensor": "Sensor"})
                mp.update_traces(marker_size=5)
                mp.for_each_trace(lambda t: t.update(name=SENSOR_LABEL.get(t.name, t.name)))
            mp.update_layout(margin=dict(l=0, r=0, t=0, b=0), legend=dict(orientation="h", y=1.02, x=0))
            st.plotly_chart(mp)
        else:
            st.info("No hotspots for these dates and sensors.")

# ---------- 3D ----------
with tab_3d:
    st.markdown("**Fire landscape.** Every peak is a month of burning: years run front to back, months left to right. "
                "Drag to rotate, scroll to zoom, hover for values. Switch to raw to see the cliff the satellites "
                "made in 2012, and how harmonization flattens it.")
    surf = st.radio("Surface", ["Harmonized", "Raw: MODIS to 2011, then VIIRS"], key="surf3d", horizontal=True)
    if surf == "Harmonized":
        s3 = harm
    else:
        mraw, vraw = column(h, "modis_cells"), column(h, "viirs_cells")
        s3 = mraw.where(mraw.index.year < 2012, vraw)
    cal3 = fc.calendar(s3)
    yrs = cal3.index.values
    land = go.Figure(go.Surface(
        z=cal3.values, x=np.arange(1, 13), y=yrs, colorscale=RAMPS[ramp], cmin=0, cmax=float(np.nanmax(fc.calendar(harm).values)),
        colorbar=dict(title=dict(text=UNIT, side="right"), thickness=12, len=0.6),
        contours=dict(z=dict(show=True, usecolormap=True, project_z=True, highlightcolor="white")),
        hovertemplate="%{y} · month %{x}<br><b>%{z:,.0f}</b> fire cell-days<extra></extra>",
        lighting=dict(ambient=0.55, diffuse=0.8, specular=0.25, roughness=0.6)))
    land.add_scatter3d(x=[0.6, 12.4], y=[2011.5, 2011.5], z=[0, 0], mode="lines+text", text=["", "VIIRS starts"],
                       line=dict(color=COLORS["VIIRS_SNPP"], width=6, dash="dash"), textfont=dict(color="#E6EAF2"),
                       hoverinfo="skip", showlegend=False)
    if sel.year in cal3.index and np.isfinite(cal3.loc[sel.year].iloc[sel.month - 1]):
        zv = float(cal3.loc[sel.year].iloc[sel.month - 1])
        land.add_scatter3d(x=[sel.month], y=[sel.year], z=[zv], mode="markers+text",
                           text=[f"{sel.strftime('%b %Y')}: {zv:,.0f}"], textposition="top center",
                           marker=dict(size=7, color="cyan", symbol="diamond", line=dict(color="white", width=2)),
                           textfont=dict(color="cyan", size=13), hoverinfo="skip", showlegend=False)
    land.update_layout(
        height=640, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
        scene=dict(xaxis=dict(title="", tickvals=list(range(1, 13)), ticktext=fc.MONTHS),
                   yaxis=dict(title="", autorange="reversed"), zaxis=dict(title=UNIT, range=[0, None]),
                   aspectratio=dict(x=1.2, y=1.7, z=0.65), camera=dict(eye=dict(x=1.9, y=-1.9, z=1.25))))
    st.plotly_chart(land)
    figs["3D fire landscape"] = land

    st.markdown("**Regions over time (3D).** Harmonized fire activity per week for 2–3 parts of the area, side by "
                "side. Every setting below is yours to change; drag to rotate.")
    o1, o2, o3, o4 = st.columns(4)
    split = o1.selectbox("Split the area", ["North → South", "West → East"])
    nreg = o2.radio("Regions", [2, 3], index=1, horizontal=True)
    step = o3.radio("Step", ["Week", "Month"], horizontal=True)
    smooth = o4.toggle("Smooth (4-step mean)", value=False)
    norm = o4.toggle("Compare shapes", value=False,
                     help="Scale each region to its own peak (100 %), so a small region's trend is visible next to a big one.")
    coord = "latitude" if split.startswith("North") else "longitude"
    with st.spinner("Counting fires per region…"):
        reg, edges = regions_over_time(country, bbox, coord, nreg, step)
    y0, y1 = st.slider("Years", int(reg.index.year.min()), int(reg.index.year.max()),
                       (max(int(reg.index.year.min()), 2012), int(reg.index.year.max())))
    rg = reg[(reg.index.year >= y0) & (reg.index.year <= y1)]
    if smooth:
        rg = rg.rolling(4, min_periods=1).mean()
    raw_rg = rg
    if norm:
        rg = 100 * rg / rg.max().replace(0, np.nan)
    zunit = "% of the region's peak" if norm else f"fire cell-days / {step.lower()}"
    xx = rg.index.year + (rg.index.dayofyear - 1) / 365.25
    zmax = float(rg.values.max()) if rg.size else 1.0
    rib = go.Figure()
    for i, name in enumerate(rg.columns):
        z = rg[name].values.astype(float)
        lo_e, hi_e = sorted((edges[::-1] if coord == "latitude" else edges)[i:i + 2])
        rng_txt = f"{lo_e:.1f}–{hi_e:.1f}° {'N' if coord == 'latitude' else 'E'}"
        rib.add_surface(x=np.vstack([xx, xx]), y=np.vstack([np.full(len(z), i - 0.32), np.full(len(z), i + 0.32)]),
                        z=np.vstack([z, z]), surfacecolor=np.vstack([z, z]), colorscale=RAMPS[ramp], cmin=0, cmax=zmax,
                        showscale=i == 0, colorbar=dict(title=dict(text="% of peak" if norm else f"per {step.lower()}", side="right"),
                                                        thickness=12, len=0.6),
                        customdata=np.vstack([rg.index.strftime("%d %b %Y")] * 2),
                        hovertemplate=f"<b>{name}</b> ({rng_txt})<br>%{{customdata}}<br>%{{z:,.0f}} {'% of peak' if norm else 'fire cell-days'}"
                                      "<extra></extra>", name=name, showlegend=False)
        rib.add_scatter3d(x=xx, y=np.full(len(z), i + 0.32), z=z, mode="lines", hoverinfo="skip",
                          line=dict(color="rgba(255,255,255,0.55)", width=2), showlegend=False)
    rib.update_layout(
        height=600, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
        scene=dict(xaxis=dict(title="", dtick=2 if y1 - y0 > 8 else 1),
                   yaxis=dict(title="", tickvals=list(range(len(rg.columns))), ticktext=list(rg.columns)),
                   zaxis=dict(title=zunit),
                   aspectratio=dict(x=2.2, y=1.0, z=0.7), camera=dict(eye=dict(x=-1.5, y=-1.9, z=1.0))))
    st.plotly_chart(rib)
    figs["Regions over time (3D)"] = rib
    rg = raw_rg
    yearly = rg.groupby(rg.index.year).sum()
    pairs = list(zip(edges[:-1], edges[1:]))[::-1] if coord == "latitude" else list(zip(edges[:-1], edges[1:]))
    summ = pd.DataFrame({"band": [f"{lo:.1f}–{hi:.1f}° {'N' if coord == 'latitude' else 'E'}" for lo, hi in pairs],
                         "mean per year": yearly.mean().round(0).astype(int).values,
                         "share of all fires": (100 * rg.sum() / rg.sum().sum()).round(1).astype(str).values + " %",
                         f"busiest {step.lower()}": [rg[c].idxmax().strftime("%d %b %Y") for c in rg.columns]},
                        index=rg.columns)
    st.dataframe(summ)
    st.caption("Bands are equal slices of the area's latitude or longitude range. Values use the same harmonization as "
               "the calendar (VIIRS units), counted per day and summed per week or month.")

# ---------- downloads ----------
with tab_data:
    out = h.drop(columns=["ym"]).copy()
    st.markdown("**Report**: summary, status and every chart in one interactive HTML file (opens in any browser).")
    blocks = [f"<p class='muted'>{place} · data through {info['complete_day']:%d %b %Y} · unit: {UNIT} "
              "(VIIRS S-NPP units)</p>",
              f"<h2>{icon} {lab}</h2><p>{head}. {nth}; median {cmp['median']:,.0f}.</p>",
              f"<p>Jan–{sel.strftime('%b')} {sel.year}: {ytd:,.0f} (median {ytd_med:,.0f}). Busiest month on record: "
              f"{rec.max():,.0f} ({rec.idxmax().strftime('%b %Y')}). Harmonization: R² {ho['r2']:.3f} on held-out years "
              f"(raw MODIS {ho['r2_raw_modis']:.3f}).</p>"]
    st.download_button("📄 Download report (HTML)", report_html(f"SYNTRA fire report: {place}", blocks, figs),
                       f"{country}_SYNTRA_report_{sel}.html", "text/html", type="primary")
    st.markdown("**Data**")
    st.download_button("⬇️ Monthly harmonized series (CSV)", out.to_csv(index=False).encode(),
                       f"{country}_monthly_harmonized.csv", "text/csv")
    st.download_button("⬇️ Burning calendar, year × month (CSV)",
                       fc.calendar(harm).to_csv().encode(), f"{country}_calendar.csv", "text/csv")
    if len(pts):
        st.download_button(f"⬇️ Hotspots {rng[0]} → {rng[1]}, sensors on the map (CSV)",
                           pts[MAP_COLS + ["sensor"]].to_csv(index=False).encode(),
                           f"{country}_hotspots_{rng[0]}_{rng[1]}.csv", "text/csv")
    st.dataframe(out.tail(36))

# ---------- method ----------
with tab_m:
    doc = hz.__doc__
    st.markdown("**Harmonization (Steps 4–5, `syntra/harmonize.py`)**\n\n"
                + doc[doc.index("1. Gridding"):doc.index("Outputs in")])
    st.markdown("**2026 (`syntra/series.py`):** months run to the last complete month. Suomi NPP data ends "
                f"{info['snpp_end']:%d %b %Y}" if info.get("snpp_end") is not None else "**2026:** archive only.")
    if info.get("snpp_end") is not None:
        st.markdown(f"From that month on VIIRS = NOAA-20 × {info['k_n20']:.3f}, the ratio of S-NPP to NOAA-20 "
                    "cell-days over every full month both flew (2018 on). \"This month so far\" compares days 1–D of "
                    "the current month with the same days of every VIIRS year.")
    st.markdown("**Cleaning (Step 3, `syntra/clean.py`):** hotspots outside the country border (Natural Earth "
                "1:10m) removed; confidence MODIS ≥ 30 ≙ VIIRS n/h; rows with no location or date and exact "
                "duplicates dropped; static sources (type 1 volcano, 2 gas flares and other static land sources, "
                "3 offshore) flagged; plus one static-source mask (~1 km cells that were static in the archive) "
                "applied to every year, so 2026 near-real-time data (no `type`) is cleaned exactly like the archive.")
    st.markdown(f"This run: {info['rows_clean']:,} clean hotspots; {info['static_by_type']:,} static by type and "
                f"{info['static_by_mask']:,} more by the mask ({info['mask_cells']:,} cells). "
                "2026 comes from the FIRMS API through `syntra/nrt.py` and is cleaned by the same code.")
    st.markdown("**Data:** NASA FIRMS (Fire Information for Resource Management System): MODIS Collection 6.1 "
                "(Terra + Aqua) and VIIRS 375 m (S-NPP, NOAA-20) yearly country archives 2000–2025, and the FIRMS "
                "area API for 2026 (standard data where available, then near-real-time). "
                "https://firms.modaps.eosdis.nasa.gov")
