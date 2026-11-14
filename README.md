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
python -m syntra.nrt            # Step 3 for 2026: FIRMS API (needs FIRMS_MAP_KEY in .env), same cleaning
python -m syntra.harmonize      # Steps 4-5: one MODIS+VIIRS series, 2000 to today, with validation
```

The last command downloads the FIRMS yearly files (Sudan, 2000 to 2025; change `DEFAULT_COUNTRY` in `syntra/data.py` for another country) into `data/raw/`. Data is not stored in git, so everyone runs it once.

Then open `notebooks/00_load_data.ipynb` and run all cells. The app runs with `streamlit run app/app.py`.

## MODIS vs VIIRS on clean data (checklist step 3)

`notebooks/02_modis_vs_viirs.ipynb` (code `syntra/compare.py`), Sudan, MODIS vs VIIRS S-NPP, 2012–2025:
- **Resolution:** VIIRS has ×4.1 MODIS's hotspots but only ×1.9 its burned 0.1° cells, steady every year. Gridding halves the gap.
- **Sensitivity:** on the same ~13:30 pass (Aqua vs S-NPP, same day, same 0.1° cell) VIIRS sees 71 % of MODIS's fire
  cells, MODIS sees 22 % of VIIRS's. The extra VIIRS fires are small: 49 % of VIIRS hotspots are below 5 MW, 0.6 % of MODIS's.
- **Season:** the cell gap is ×1.4 in November but ×6.8 in July (few, small wet-season fires), so the factor must be per month.

## Harmonization (phases 4 and 5)

Code: `syntra/harmonize.py` (method in its docstring and `docs/MODIS_vs_VIIRS.md`).
1. Count **burned 0.1° cells per month** (about 11 km) instead of raw hotspots, per sensor.
2. MODIS Terra-only months (Nov 2000–Jun 2002) are scaled to Terra + Aqua (monthly factor, fitted 2003–2021).
3. A monthly factor VIIRS / MODIS, fitted on the 2012–2021 overlap, converts MODIS into VIIRS units. The series
   uses observed VIIRS from 2012 and MODIS × factor before that.
4. Validation is leave-one-year-out: each overlap year is predicted from MODIS by factors that never saw it.

`syntra/series.py` extends this to 2026 for the app: months run to the last complete month, and after Suomi NPP's
data ends (2 Nov 2026) VIIRS = NOAA-20 cells × k (S-NPP / NOAA-20, fitted on every month both flew, 2018 on).

```bash
python scripts/validate_harmonization.py --countries Sudan Ethiopia Iraq Saudi_Arabia
```

Monthly R², leave-one-year-out 2012–2021 (120 months per country), archive data:

| Country | R² raw MODIS | **R² harmonized** | Median annual error | Median monthly r |
| --- | --- | --- | --- | --- |
| Sudan | 0.39 | **0.97** | 3.0 % | 0.99 |
| Ethiopia | 0.55 | **0.98** | 4.3 % | 0.99 |
| Iraq | 0.34 | **0.83** | 9.6 % | 0.97 |
| Saudi Arabia | −20.7 | **−0.75** | 7.0 % | 0.44 |

Saudi Arabia has few, scattered vegetation fires (about 1,700 burned cells a year), so its monthly signal is noisy:
the yearly totals are close (7 % error) but single months are not. It shows where the method reaches its limits.
Tables: `outputs/tables/harmonization_validation.csv` and `harmonization_validation_by_year.csv`.

Slide figures: `notebooks/01_harmonization.ipynb` writes them to `outputs/figures/` (code in `syntra/figures.py`).

## App

`streamlit run app/app.py`. Pick a country, then optionally draw a rectangle on the map or type lat/lon. The app
shows the harmonized year × month burning calendar, the selected month vs its historical median, the
validation, a hotspot map and CSV downloads. Data is downloaded from FIRMS on first use (a few minutes).

**2026 data** comes from the FIRMS API and needs a free MAP_KEY: copy `.env.example` to `.env` and fill in
`FIRMS_MAP_KEY` (never commit `.env`). On Streamlit Cloud put the same line in the app's Secrets. Without a key the
app still works on the archive (to Dec 2025). The whole chain (fetch → `syntra/clean.py` → 2026 → static mask →
harmonization) is `syntra/pipeline.py` (this year from `syntra/nrt.py`):

```python
from syntra.pipeline import load_country
from syntra import series
d = load_country("Sudan")                       # d["veg"], d["static"], d["info"]
s = series.country_series(d["veg"], d["info"])  # s["tab"] = monthly harmonized table, s["validation"], ...
```

To save the cleaned and harmonized data for one country (2000 to yesterday) into `data/processed/`:

```bash
python -m syntra.pipeline --country Sudan
```

Small copies of the Sudan results are in `outputs/tables/` (`harmonized_Sudan.csv`, `factors_Sudan.csv`,
`validation_Sudan.csv`, `run_info_Sudan.json`).

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
