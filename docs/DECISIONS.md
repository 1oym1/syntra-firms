# Decisions

Short record of decisions the team has agreed on. Newest first.

## 2026-11-14: Count vegetation fires only (`type = 0`)

**Decision.** We keep only hotspots with `type = 0` ("presumed vegetation fire") and drop volcanoes (1), static land sources such as gas flares (2) and offshore sources (3). For 2026 NRT data, which has no `type` field, we drop hotspots that fall in a static-source mask built from the archive. Details: [FIRE_SOURCE.md](FIRE_SOURCE.md).

## 2026-11-14: Build and test on Sudan

**Decision.** Sudan is our working area: we build the harmonization code and algorithm on it, and test and calibrate there. It is set once in `syntra/data.py` as `DEFAULT_COUNTRY = "Sudan"`. The fetch script, the notebooks and the app all read it from there.

**Why.** Based on `outputs/tables/sensor_agreement_2025.csv`:

| Country | VIIRS/MODIS ratio | Daily r | Monthly r | Active months | Score |
| --- | --- | --- | --- | --- | --- |
| **Sudan** | 5.45× | 0.86 | 0.99 | 11 | 0.62 |
| Saudi Arabia | 9.97× | 0.12 | 0.46 | 5 | −0.17 |

- The two sensors agree well in Sudan (monthly r 0.99), so a harmonization factor can be fitted and validated there (Steps 4 and 5).
- There is fire activity in 11 months of the year, with a strong seasonal cycle, which gives a clear burning calendar.
- It is across the Red Sea from Jeddah, so it is relevant to our region and to the story we tell.
- Saudi Arabia has too few fires and too little agreement between the sensors to calibrate on (daily r 0.12). We keep it as the "hard case" in the presentation, to show why cleaning out static sources such as gas flares matters.

The app still works for any area the user draws. The country only decides which data we download and calibrate on.

**Confirmed over 14 years (PR #1).** Leave-one-year-out validation 2012–2025 of our harmonization (each year predicted
by a model that never saw it) gives **R² 0.99** for Sudan, Ethiopia 0.97, Iraq 0.88, Saudi Arabia 0.28. See
`outputs/tables/harmonization_validation.csv`. Saudi Arabia's weak result is shown honestly as the limits case.

**Next.** We build everything on Sudan first and may add a second country later. Ethiopia is ready (validated,
R² 0.97) and is also the backup if Sudan causes a problem. The app accepts any FIRMS country, so adding one needs
no code change, only its figures for the slides.

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
