"""SYNTRA fire calendar web app (Streamlit).

Run from the repo root:
    streamlit run app/app.py

Data: syntra.pipeline (FIRMS yearly files 2000-2025 + 2026 from the FIRMS API, cleaned by syntra.clean),
harmonization from syntra.harmonize, the calendar from syntra.fire_calendar.
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
from syntra.data import DEFAULT_COUNTRY  # noqa: E402
from syntra.pipeline import load_country  # noqa: E402

COUNTRIES = ["Sudan", "Ethiopia", "Iraq", "Saudi_Arabia", "Australia", "Zambia", "South_Sudan", "Mexico"]
COLORS = {"MODIS": "#E69F00", "VIIRS_SNPP": "#56B4E9", "VIIRS_NOAA20": "#CC79A7", "harmonized": "#009E73",
          "Static source": "#D55E00"}  # Okabe-Ito, colorblind-safe

st.set_page_config(page_title="SYNTRA fire calendar", page_icon="🔥", layout="wide")


# ---------- data ----------
try:  # deployed: key in Streamlit secrets; local: .env (read by syntra.recent)
    if "FIRMS_MAP_KEY" in st.secrets:
        os.environ.setdefault("FIRMS_MAP_KEY", st.secrets["FIRMS_MAP_KEY"])
except Exception:  # noqa: BLE001  (no secrets file)
    pass


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def get_country(country):
    return load_country(country)


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def side_checks(country):
    d = get_country(country)
    return hz.validate_noaa20(d["cells"], d["info"]["snpp_end"]), hz.validate_terra(d["cells"])


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def analyse(country, bbox):
    d = get_country(country)
    info = d["info"]
    cells = hz.in_bbox(d["cells"], bbox)
    day = info["complete_day"]
    last_full = (day + pd.Timedelta(days=1)).to_period("M") - 1
    mon = hz.monthly(cells, last_full, info["snpp_end"], info["k_noaa20"], info["terra_k"])
    coef = hz.fit_model(mon)
    mtd = None
    if day.to_period("M") > last_full:
        daily = hz.daily_reference(cells, coef, info["snpp_end"], info["k_noaa20"], info["terra_k"])
        mtd = fc.month_to_date(daily, day)
    return cells, hz.harmonize(mon, coef), hz.validate(mon), coef, mtd


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
        all_cells, info = data["cells"], data["info"]
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not load '{country}': {e}")
        st.stop()
if all_cells.empty:
    st.error(f"No FIRMS data for '{country}'. Check the spelling (FIRMS uses underscores).")
    st.stop()

with st.sidebar:
    st.subheader("Area of interest")
    mode = st.radio("Area", ["Whole country", "Draw on map", "Type lat/lon"], label_visibility="collapsed")
    bbox = None
    if mode == "Type lat/lon":
        c1, c2 = st.columns(2)
        w = c1.number_input("West", value=float(round(all_cells.longitude.min(), 2)), step=0.5)
        e = c2.number_input("East", value=float(round(all_cells.longitude.max(), 2)), step=0.5)
        s = c1.number_input("South", value=float(round(all_cells.latitude.min(), 2)), step=0.5)
        n = c2.number_input("North", value=float(round(all_cells.latitude.max(), 2)), step=0.5)
        bbox = (w, s, e, n)

if mode == "Draw on map":
    st.markdown("**Draw a rectangle** with the ■ tool on the left of the map, then the page updates.")
    m = folium.Map(location=[all_cells.latitude.median(), all_cells.longitude.median()], zoom_start=5,
                   tiles="OpenStreetMap")
    Draw(draw_options={"rectangle": True, "polygon": False, "polyline": False, "circle": False,
                       "marker": False, "circlemarker": False}, edit_options={"edit": False}).add_to(m)
    drawn = st_folium(m, height=380, use_container_width=True, returned_objects=["last_active_drawing"])
    bbox = bbox_from_drawing((drawn or {}).get("last_active_drawing"))
    if bbox is None:
        st.info("No rectangle yet: showing the whole country.")

cells, h, val, coef, mtd = analyse(country, bbox)
if h["harmonized"].sum() == 0:
    st.warning("No vegetation fires in this area. Draw a bigger box.")
    st.stop()

with st.sidebar:
    months = [m for m in h.index[::-1] if not np.isnan(h.loc[m, "harmonized"])]
    sel = st.selectbox("Month to compare", months, format_func=lambda p: p.strftime("%B %Y"))
    view = st.radio("Calendar shows", ["Harmonized", "Raw MODIS", "Raw VIIRS"])
    ramp = st.selectbox("Color ramp (colorblind-safe)", ["Inferno", "Cividis", "Viridis"])
    st.caption(f"Data through **{info['complete_day']:%d %b %Y}**. "
               + ("2026 from the FIRMS API (near-real-time, provisional)." if info.get("key")
                  else "No FIRMS_MAP_KEY set: archive only (to Dec 2025)."))

series = {"Harmonized": h["harmonized"], "Raw MODIS": h["modis"], "Raw VIIRS": h["viirs"]}[view]
cmp = fc.month_vs_median(h["harmonized"], sel)

# ---------- header + KPIs ----------
place = country.replace("_", " ") + ("" if bbox is None else f" · box W{bbox[0]} S{bbox[1]} E{bbox[2]} N{bbox[3]}")
st.header(f"Burning activity: {place}")
st.caption("Unit: **fire-cells**, i.e. unique ~1 km grid cells with a vegetation-fire detection per day, "
           "summed per month, in VIIRS-equivalent units. Source: NASA FIRMS.")

k1, k2, k3, k4 = st.columns(4)
k1.metric(sel.strftime("%b %Y"), f"{cmp['value']:,.0f}",
          f"{cmp['anomaly_pct']:+.0f}% vs median" if np.isfinite(cmp["anomaly_pct"]) else None,
          delta_color="inverse")
k2.metric(f"Historical median ({sel.strftime('%B')})", f"{cmp['median']:,.0f}", f"{cmp['n_years']} years",
          delta_color="off")
k3.metric("Rank among same months", f"#{cmp['rank']} of {cmp['n_years'] + 1}" if cmp["rank"] else "n/a")
k4.metric("Harmonization skill (R², held-out years)", f"{val['harmonized']['r2']:.2f}",
          f"raw MODIS: {val['raw_modis']['r2']:.2f}", delta_color="off")

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
    m3.metric("Rank among the same days", f"#{mtd['rank']} of {mtd['n_years'] + 1}" if mtd["rank"] else "n/a")
    note = ("Same days of the month in every year, so a part month is compared fairly. ")
    if info.get("snpp_end") is not None and day > info["snpp_end"]:
        note += (f"Suomi NPP stopped on {info['snpp_end']:%d %b %Y}; days after that use VIIRS NOAA-20 × "
                 f"{info['k_noaa20']:.3f} (S-NPP-equivalent). ")
    st.caption(note + "Near-real-time data: provisional.")

tab_cal, tab_h, tab_map, tab_data, tab_m = st.tabs(
    ["📅 Burning calendar", "🛰️ Harmonization", "🗺️ Hotspot map", "⬇️ Download", "📖 Method"])

# ---------- calendar ----------
with tab_cal:
    cal = fc.calendar(series)
    fig = px.imshow(cal, color_continuous_scale=ramp, aspect="auto", text_auto=".0f",
                    labels=dict(x="Month", y="Year", color="fire-cells"))
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
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        same = h["harmonized"][h.index.month == sel.month].dropna()
        bar = go.Figure(go.Bar(x=same.index.year, y=same.values,
                               marker_color=[COLORS["harmonized"] if p == sel else "#999" for p in same.index]))
        bar.add_hline(y=cmp["median"], line_dash="dash", annotation_text="historical median")
        bar.update_layout(title=f"Every {sel.strftime('%B')} since 2000", height=320,
                          margin=dict(l=0, r=0, t=40, b=0), yaxis_title="fire-cells")
        st.plotly_chart(bar, use_container_width=True)
    with c2:
        hist = h["harmonized"][h.index.year < sel.year]
        st.markdown("**Fire season at a glance**")
        st.markdown(f"- Peak months (median): **{', '.join(fc.peak_months(fc.calendar(hist)))}**")
        top = fc.busiest_years(h["harmonized"])
        st.markdown("- Busiest full years: " + ", ".join(f"**{y}** ({v:,.0f})" for y, v in top.items()))
        st.markdown(f"- {sel.strftime('%B %Y')}: **{cmp['value']:,.0f}** fire-cells vs median "
                    f"**{cmp['median']:,.0f}** ({cmp['anomaly_pct']:+.0f}%)")

# ---------- harmonization ----------
with tab_h:
    st.markdown("**Why harmonize?** VIIRS (375 m) sees many more and smaller fires than MODIS (1 km). "
                "Plotted raw, the record seems to jump in 2012 when VIIRS starts. "
                "After harmonization the sensor of origin no longer matters.")
    t = h.index.to_timestamp()
    ts = go.Figure()
    ts.add_scatter(x=t, y=h["modis"], name="Raw MODIS", line_color=COLORS["MODIS"])
    ts.add_scatter(x=t, y=h["viirs"], name="Raw VIIRS (S-NPP)", line_color=COLORS["VIIRS_SNPP"])
    ts.add_scatter(x=t, y=h["modis_scaled"], name="MODIS converted to VIIRS-equivalent",
                   line=dict(color=COLORS["harmonized"], dash="dot"))
    ts.update_layout(height=380, margin=dict(l=0, r=0, t=30, b=0), yaxis_title="fire-cells / month",
                     legend=dict(orientation="h"))
    st.plotly_chart(ts, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        p = val["predictions"]
        sc = go.Figure()
        sc.add_scatter(x=p["viirs"], y=p["modis"], mode="markers", name="Raw MODIS",
                       marker_color=COLORS["MODIS"], opacity=0.6)
        sc.add_scatter(x=p["viirs"], y=p["pred"], mode="markers", name="Harmonized (held-out year)",
                       marker_color=COLORS["harmonized"], opacity=0.7)
        mx = float(p["viirs"].max())
        sc.add_scatter(x=[0, mx], y=[0, mx], mode="lines", name="perfect agreement",
                       line=dict(color="gray", dash="dash"))
        sc.update_layout(title="Predicted vs observed VIIRS, leave-one-year-out", height=420,
                         xaxis_title="observed VIIRS", yaxis_title="estimate",
                         margin=dict(l=0, r=0, t=70, b=0), legend=dict(orientation="h", y=1.0, yanchor="bottom"))
        st.plotly_chart(sc, use_container_width=True)
    with c2:
        tbl = pd.DataFrame({k: val[k] for k in ("raw_modis", "ratio", "harmonized")}).T
        tbl.index = ["Raw MODIS (no correction)", "Seasonal ratio (baseline)", "Seasonal linear model (ours)"]
        tbl.columns = ["R²", "Mean abs. error", "Bias %", "Correlation r"]
        st.markdown(f"**Validation**: {val['n_months']} months, {val['years'][0]}–{val['years'][-1]}, "
                    "each year predicted by a model that never saw it.")
        st.dataframe(tbl.style.format("{:.2f}"), use_container_width=True)
        st.markdown(f"Model: `VIIRS = a(month) + {coef[0]:.2f} × MODIS`")
        vn, vt = side_checks(country)
        if vt:
            st.markdown(f"**MODIS Terra-only months (Nov 2000–Jun 2002)** scaled to Terra + Aqua with a factor per "
                        f"month (median {vt['k'].median():.2f}); held-out years {vt['years'][0]}–{vt['years'][-1]}: "
                        f"R² {vt['metrics']['r2']:.3f}.")
        if vn:
            st.markdown(f"**NOAA-20 → S-NPP (for days after S-NPP stopped):** k = {vn['k']:.3f}; "
                        f"{vn['n_months']} months both flew, held-out R² {vn['converted']['r2']:.3f}, "
                        f"bias {vn['converted']['bias_pct']:+.1f} %.")
        ab = go.Figure(go.Bar(x=fc.MONTHS, y=coef[1:], marker_color=COLORS["VIIRS_SNPP"]))
        ab.update_layout(title="a(month): small fires only VIIRS detects", height=220,
                         margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(ab, use_container_width=True)

# ---------- hotspot map ----------
with tab_map:
    d0 = sel.to_timestamp().date()
    d1 = (sel + 1).to_timestamp().date() - pd.Timedelta(days=1)
    rng = st.date_input("Date range", (d0, d1), min_value=cells.date.min().date(), max_value=cells.date.max().date())
    pts = cells.iloc[0:0]
    if isinstance(rng, (tuple, list)) and len(rng) == 2:
        pts = cells[cells.date.between(pd.Timestamp(rng[0]), pd.Timestamp(rng[1]))]
        show_static = st.toggle("Show static sources (gas flares, refineries)", value=False)
        st.caption(f"{len(pts):,} fire-cells ({(pts.sensor == 'VIIRS_SNPP').sum():,} VIIRS S-NPP, "
                   f"{(pts.sensor == 'VIIRS_NOAA20').sum():,} VIIRS NOAA-20, {(pts.sensor == 'MODIS').sum():,} MODIS). "
                   "Calendar and anomalies always use vegetation fires only.")
        show = pts.sample(30000, random_state=0) if len(pts) > 30000 else pts
        if show_static:
            stc = data["static"]
            stc = stc[stc.acq_date.between(pd.Timestamp(rng[0]), pd.Timestamp(rng[1]))]
            if bbox is not None:
                stc = stc[stc.longitude.between(bbox[0], bbox[2]) & stc.latitude.between(bbox[1], bbox[3])]
            show = pd.concat([show, stc.assign(sensor="Static source", date=stc.acq_date)[
                ["sensor", "date", "latitude", "longitude", "frp"]]], ignore_index=True)
        mp = px.scatter_map(show, lat="latitude", lon="longitude", color="sensor", hover_data=["date", "frp"],
                            color_discrete_map=COLORS, height=560, map_style="carto-darkmatter",
                            center=dict(lat=float(cells.latitude.median()), lon=float(cells.longitude.median())),
                            zoom=4.3)
        mp.update_traces(marker_size=5)
        mp.update_layout(margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(mp, use_container_width=True)

# ---------- downloads ----------
with tab_data:
    out = h.copy()
    out.index = out.index.astype(str)
    out = out.rename(columns={"modis": "modis_raw", "viirs": "viirs_raw", "modis_scaled": "modis_as_viirs"})
    st.download_button("⬇️ Monthly harmonized series (CSV)", out.to_csv().encode(),
                       f"{country}_monthly_harmonized.csv", "text/csv")
    st.download_button("⬇️ Burning calendar, year × month (CSV)",
                       fc.calendar(h["harmonized"]).to_csv().encode(), f"{country}_calendar.csv", "text/csv")
    if len(pts):
        st.download_button(f"⬇️ Hotspots {rng[0]} → {rng[1]} (CSV)",
                           pts.drop(columns=["cell_y", "cell_x", "seen_by_terra"]).to_csv(index=False).encode(),
                           f"{country}_hotspots_{rng[0]}_{rng[1]}.csv", "text/csv")
    st.dataframe(out.tail(36), use_container_width=True)

# ---------- method ----------
with tab_m:
    st.markdown(hz.__doc__.split("    from syntra")[0])
    st.markdown("**Cleaning (Step 3, `syntra/clean.py`):** confidence MODIS ≥ 30 ≙ VIIRS n/h; rows with no "
                "location or date and exact duplicates dropped; static sources (type 1 volcano, 2 gas flares and "
                "other static land sources, 3 offshore) flagged; plus one static-source mask (~1 km cells that were "
                "static in the archive or burned on more than half the days of a year) applied to every year, "
                "so 2026 near-real-time data (no `type`) is cleaned exactly like the archive.")
    st.markdown(f"This run: {info['rows_clean']:,} clean hotspots; {info['static_by_type']:,} static by type and "
                f"{info['static_by_mask']:,} more by the mask ({info['mask_cells']:,} cells); "
                f"{info.get('dropped_outside', 0):,} 2026 API hotspots outside the country removed.")
    st.markdown("**Data:** NASA FIRMS (Fire Information for Resource Management System): MODIS Collection 6.1 "
                "(Terra + Aqua) and VIIRS 375 m (S-NPP, NOAA-20) yearly country archives 2000–2025, and the FIRMS "
                "area API for 2026 (standard data where available, then near-real-time). "
                "https://firms.modaps.eosdis.nasa.gov")
