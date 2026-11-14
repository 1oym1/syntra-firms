# Decisions

Short record of decisions the team has agreed on. Newest first.

## 2026-11-14: Sudan is our main study area

**Decision.** Sudan is the main example for the harmonization, the app (default country) and the presentation.
Saudi Arabia stays as a comparison case that shows the limits of the method. Agreed by the team; recorded by Hisham.

**Why.**
- Ahmad's 2025 screen (`country_recommendation`): mostly vegetation fires (type 0), thousands of hotspots a month,
  a clear fire season, high MODIS–VIIRS agreement, a manageable data size, and close to Saudi Arabia.
- Confirmed over 14 years, not only 2025: leave-one-year-out validation 2012–2025 gives **R² 0.99** for Sudan
  (Ethiopia 0.97, Iraq 0.88, Saudi Arabia 0.28). See `outputs/tables/harmonization_validation.csv`.
- Saudi Arabia has few, scattered vegetation fires (most raw hotspots are gas flares and other static sources), so its
  conversion is weak (R² 0.28). Showing it honestly strengthens the Validity criterion.

**Next.** We build everything on Sudan first. We may add a second country later. Ethiopia is ready
(already validated, R² 0.97), and it is also the backup if Sudan causes a problem. The app already accepts
any FIRMS country, so adding one needs no code change, only its figures for the slides.

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
