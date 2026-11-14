# SYNTRA | MODIS + VIIRS Fire Hotspot Harmonization

Team SYNTRA's project for the **NASA Space Apps Challenge 2026** (Jeddah), challenge [Harmonization of MODIS and VIIRS Hot Spots](https://www.spaceappschallenge.org/2026/challenges/modis-and-viirs-hot-spots/).

Satellites have recorded fire hotspots since 2000, but the record is split between two sensors: MODIS (about 1 km pixels, 2000 to now) and VIIRS (about 375 m pixels, 2012 to now). Their counts cannot be compared directly. We merge them into one consistent record and show it as a burning-activity calendar for an area the user picks.

## Team

Riyadh Barnawi (team owner), Yazeed Firas, Obai Merdad, Ahmad Qadah, Hisham Albaiti.

## Quick start

```bash
git clone https://github.com/1oym1/syntra-firms.git
cd syntra-firms
pip install -r requirements.txt
python scripts/fetch_firms.py
python -m syntra.clean          # Step 3: clean the data (see syntra/clean.py)
```

The last command downloads the FIRMS yearly files (Sudan, 2000 to 2025; change `DEFAULT_COUNTRY` in `syntra/data.py` for another country) into `data/raw/`. Data is not stored in git, so everyone runs it once.

Then open `notebooks/00_load_data.ipynb` and run all cells. The app runs with `streamlit run app/app.py`.

## Harmonization (phases 4 and 5)

Code: `syntra/harmonize.py`. Hotspots are snapped to a ~1 km grid and counted as unique fire-cells per day.
On the 2012–2025 overlap we fit `VIIRS = a(month) + b × MODIS`, then convert MODIS 2000–2011 into
VIIRS-equivalent units. Validation is leave-one-year-out: each year is predicted by a model that never saw it.

```bash
python scripts/validate_harmonization.py --countries Sudan Ethiopia Iraq Saudi_Arabia
```

| Country | R² raw MODIS | R² seasonal ratio | **R² our model** | Bias (model) |
| --- | --- | --- | --- | --- |
| Sudan | 0.31 | 0.99 | **0.99** | −0.1 % |
| Ethiopia | 0.21 | 0.97 | **0.97** | 0.0 % |
| Iraq | −0.27 | 0.71 | **0.88** | +0.2 % |
| Saudi Arabia | −11.0 | −0.71 | **0.28** | +0.1 % |

Saudi Arabia has few, scattered vegetation fires, so its monthly signal is noisy. It shows where the method
reaches its limits. Full table: `outputs/tables/harmonization_validation.csv`.

## App

`streamlit run app/app.py`. Pick a country, then optionally draw a rectangle on the map or type lat/lon. The app
shows the harmonized year × month burning calendar, the selected month vs its historical median, the
validation, a hotspot map and CSV downloads. Data is downloaded from FIRMS on first use (a few minutes).

**2026 data** comes from the FIRMS API and needs a free MAP_KEY: copy `.env.example` to `.env` and fill in
`FIRMS_MAP_KEY` (never commit `.env`). On Streamlit Cloud put the same line in the app's Secrets. Without a key the
app still works on the archive (to Dec 2025). The whole chain (fetch → `syntra/clean.py` → 2026 → static mask →
fire-cells) is `syntra/pipeline.py`:

```python
from syntra.pipeline import load_country
d = load_country("Sudan")   # d["cells"], d["static"], d["info"]
```

## Folders

```
syntra-firms/
├── syntra/          shared Python code (loading, harmonization). Notebooks and the app import it.
├── notebooks/       one notebook per phase: 00_load_data, 01_harmonization, ...
├── app/             the Streamlit web app
├── scripts/         command-line helpers (data download)
├── outputs/
│   ├── figures/     PNG charts for the slides
│   └── tables/      small result tables (CSV under 1 MB)
├── presentation/    slides and the 30-second video
├── docs/            team guide and method notes
└── data/            raw/ and processed/ FIRMS files, NOT in git
```

## Data

[NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) active fire data: MODIS Collection 6.1 and VIIRS 375 m (Suomi NPP and NOAA-20). Column meanings: [FIRMS attribute definitions](https://www.earthdata.nasa.gov/data/tools/firms/active-fire-data-attributes-modis-viirs).

New to the sensors? Read [docs/MODIS_vs_VIIRS.md](docs/MODIS_vs_VIIRS.md) (what MODIS and VIIRS are, how they differ, and our harmonization plan; English + Arabic, with a one-page [PDF](docs/MODIS_vs_VIIRS.pdf)). Which fires we count and which we drop: [docs/FIRE_SOURCE.md](docs/FIRE_SOURCE.md).

## Working together

Read [docs/TEAM_GUIDE.md](docs/TEAM_GUIDE.md) before your first commit.
