"""SYNTRA fire calendar web app (Streamlit).

Run from the repo root:
    streamlit run app/app.py

Data: syntra.pipeline (FIRMS yearly files 2000-2025 + 2026 from the FIRMS API, cleaned by syntra.clean).
Harmonization: syntra.harmonize (burned 0.1 degree cells per month, MODIS -> VIIRS monthly factors),
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
UNIT = "burned cells"
MAP_COLS = ["latitude", "longitude", "acq_date", "acq_time", "satellite", "frp", "daynight", "type"]

st.set_page_config(page_title="SYNTRA fire calendar", page_icon="🔥", layout="wide")


# ---------- data ----------
try:  # deployed: key in Streamlit secrets; local: .env (read by syntra.recent)
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

# ---------- header + KPIs ----------
place = country.replace("_", " ") + ("" if bbox is None else f" · box W{bbox[0]} S{bbox[1]} E{bbox[2]} N{bbox[3]}")
st.header(f"Burning activity: {place}")
st.caption("Unit: **burned cells**, the number of 0.1° grid cells (about 11 km) with at least one vegetation-fire "
           "detection in the month, in VIIRS S-NPP units. Measures how widespread burning is, not how often the "
           "same place burns. Source: NASA FIRMS.")

k1, k2, k3, k4 = st.columns(4)
k1.metric(sel.strftime("%b %Y"), f"{cmp['value']:,.0f}",
          f"{cmp['anomaly_pct']:+.0f}% vs median" if np.isfinite(cmp["anomaly_pct"]) else None,
          delta_color="inverse")
k2.metric(f"Historical median ({sel.strftime('%B')})", f"{cmp['median']:,.0f}", f"{cmp['n_years']} years",
          delta_color="off")
k3.metric("Rank among same months", f"#{cmp['rank']} of {cmp['n_years'] + 1}" if cmp["rank"] else "n/a")
k4.metric("Harmonization skill (R², held-out years)", f"{ho['r2']:.2f}", f"raw MODIS: {ho['r2_raw_modis']:.2f}",
          delta_color="off")

if np.isfinite(cmp["p90"]) and cmp["value"] > cmp["p90"]:
    st.warning(f"⚠️ {sel.strftime('%B %Y')} is above the 90th percentile of all previous "
               f"{sel.strftime('%B')}s: an unusually active month.")

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

tab_cal, tab_h, tab_map, tab_data, tab_m = st.tabs(
    ["📅 Burning calendar", "🛰️ Harmonization", "🗺️ Hotspot map", "⬇️ Download", "📖 Method"])

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

    c1, c2 = st.columns(2)
    with c1:
        same = harm[harm.index.month == sel.month].dropna()
        bar = go.Figure(go.Bar(x=same.index.year, y=same.values,
                               marker_color=[COLORS["harmonized"] if p == sel else "#999" for p in same.index]))
        bar.add_hline(y=cmp["median"], line_dash="dash", annotation_text="historical median")
        bar.update_layout(title=f"Every {sel.strftime('%B')} since 2000", height=320,
                          margin=dict(l=0, r=0, t=40, b=0), yaxis_title=UNIT)
        st.plotly_chart(bar)
    with c2:
        hist = harm[harm.index.year < sel.year]
        st.markdown("**Fire season at a glance**")
        if len(hist.dropna()):
            st.markdown(f"- Peak months (median): **{', '.join(fc.peak_months(fc.calendar(hist)))}**")
        top = fc.busiest_years(harm)
        st.markdown("- Busiest full years: " + ", ".join(f"**{y}** ({v:,.0f})" for y, v in top.items()))
        st.markdown(f"- {sel.strftime('%B %Y')}: **{cmp['value']:,.0f}** {UNIT} vs median "
                    f"**{cmp['median']:,.0f}** ({cmp['anomaly_pct']:+.0f}%)")
        src = h.loc[(h.year == sel.year) & (h.month == sel.month), "source"]
        if len(src):
            st.markdown(f"- Source of {sel.strftime('%b %Y')}: {src.iloc[0]}")

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
    d0 = sel.to_timestamp().date()
    d1 = min((sel + 1).to_timestamp().date() - pd.Timedelta(days=1), info["complete_day"].date())
    rng = st.date_input("Date range", (d0, d1), min_value=veg.acq_date.min().date(),
                        max_value=info["complete_day"].date())
    pts = pts_all.iloc[0:0]
    if isinstance(rng, (tuple, list)) and len(rng) == 2:
        pts = pts_all[pts_all.acq_date.between(pd.Timestamp(rng[0]), pd.Timestamp(rng[1]))]
        pts = pts.assign(sensor=pts.satellite.map(SENSOR))
        show_static = st.toggle("Show static sources (gas flares, refineries)", value=False)
        st.caption(f"{len(pts):,} hotspots ({(pts.sensor == 'VIIRS_SNPP').sum():,} VIIRS S-NPP, "
                   f"{(pts.sensor == 'VIIRS_NOAA20').sum():,} VIIRS NOAA-20, {(pts.sensor == 'MODIS').sum():,} MODIS). "
                   "Calendar and anomalies use vegetation fires only.")
        show = pts.sample(30000, random_state=0) if len(pts) > 30000 else pts
        show = show[["sensor", "acq_date", "latitude", "longitude", "frp"]]
        if show_static:
            stc = in_box(data["static"], bbox)
            stc = stc[stc.acq_date.between(pd.Timestamp(rng[0]), pd.Timestamp(rng[1]))]
            show = pd.concat([show, stc.assign(sensor="Static source")[show.columns]], ignore_index=True)
        if len(show):
            mp = px.scatter_map(show, lat="latitude", lon="longitude", color="sensor", hover_data=["acq_date", "frp"],
                                color_discrete_map=COLORS, height=560, map_style="carto-darkmatter",
                                center=dict(lat=float(pts_all.latitude.median()), lon=float(pts_all.longitude.median())),
                                zoom=4.3)
            mp.update_traces(marker_size=5)
            mp.update_layout(margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(mp)
        else:
            st.info("No hotspots in this date range.")

# ---------- downloads ----------
with tab_data:
    out = h.drop(columns=["ym"]).copy()
    st.download_button("⬇️ Monthly harmonized series (CSV)", out.to_csv(index=False).encode(),
                       f"{country}_monthly_harmonized.csv", "text/csv")
    st.download_button("⬇️ Burning calendar, year × month (CSV)",
                       fc.calendar(harm).to_csv().encode(), f"{country}_calendar.csv", "text/csv")
    if len(pts):
        st.download_button(f"⬇️ Hotspots {rng[0]} → {rng[1]} (CSV)",
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
        st.markdown(f"From that month on VIIRS = NOAA-20 cells × {info['k_n20']:.3f}, the ratio of S-NPP to NOAA-20 "
                    "cells over every full month both flew (2018 on). \"This month so far\" compares days 1–D of "
                    "the current month with the same days of every VIIRS year.")
    st.markdown("**Cleaning (Step 3, `syntra/clean.py`):** hotspots outside the country border (Natural Earth "
                "1:10m) removed; confidence MODIS ≥ 30 ≙ VIIRS n/h; rows with no location or date and exact "
                "duplicates dropped; static sources (type 1 volcano, 2 gas flares and other static land sources, "
                "3 offshore) flagged; plus one static-source mask (~1 km cells that were static in the archive) "
                "applied to every year, so 2026 near-real-time data (no `type`) is cleaned exactly like the archive.")
    st.markdown(f"This run: {info['rows_clean']:,} clean hotspots; {info['static_by_type']:,} static by type and "
                f"{info['static_by_mask']:,} more by the mask ({info['mask_cells']:,} cells); "
                f"{info.get('dropped_outside', 0):,} 2026 API hotspots outside the country removed.")
    st.markdown("**Data:** NASA FIRMS (Fire Information for Resource Management System): MODIS Collection 6.1 "
                "(Terra + Aqua) and VIIRS 375 m (S-NPP, NOAA-20) yearly country archives 2000–2025, and the FIRMS "
                "area API for 2026 (standard data where available, then near-real-time). "
                "https://firms.modaps.eosdis.nasa.gov")
