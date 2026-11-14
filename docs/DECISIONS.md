# Decisions

Short record of decisions the team has agreed on. Newest first.

## 2026-11-14: The app is built with Streamlit

**Decision.** The web app is built with Streamlit (`app/app.py`). We do not use FastAPI + Leaflet.

**Why.**
- NASA Space Apps requires no particular framework. Judges score Impact, Creativity, Validity, Relevance and Presentation, and every team must submit a demo.
- The hackathon runs only from Nov 14 to Nov 15, and the app already exists in Streamlit. Rebuilding it in another stack would waste time.
- Streamlit covers every required output:
  - drawing an area of interest on a map, or typing lat/lon (`streamlit-folium`)
  - the months × years burning calendar with a colorblind-friendly ramp (Plotly)
  - the current month compared with the historical median, with anomalies highlighted
  - CSV download of hotspots and analytics (`st.download_button`)
- It deploys free on Streamlit Community Cloud, so judges get a live link.

**Stack.**
| Layer | Tool |
| --- | --- |
| Data and analysis | Python: pandas, geopandas, numpy (`syntra/`, `notebooks/`) |
| App | Streamlit + streamlit-folium (map) + Plotly (charts) |
| Deploy | Streamlit Community Cloud |
| Run locally | `streamlit run app/app.py` |

Shared logic lives in `syntra/` and is imported by both the notebooks and the app, so the harmonization code exists in one place only.
