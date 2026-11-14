"""SYNTRA fire calendar web app (Streamlit). Placeholder until phase 6.

Run from the repo root:
    streamlit run app/app.py
"""
import pathlib
import sys

import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from syntra.data import DEFAULT_COUNTRY, load_fires  # noqa: E402

st.set_page_config(page_title="SYNTRA fire calendar", layout="wide")
st.title("SYNTRA | Fire activity calendar")
st.caption("MODIS + VIIRS hotspots from NASA FIRMS. Harmonization not applied yet.")


@st.cache_data
def get_fires():
    return load_fires(DEFAULT_COUNTRY, download=False)


fires = get_fires()
st.metric("Vegetation hotspots loaded", f"{len(fires):,}")
st.bar_chart(fires.groupby(["year", "sensor"]).size().unstack(fill_value=0))
