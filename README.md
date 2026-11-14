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
```

The last command downloads the FIRMS yearly files (Saudi Arabia, 2000 to 2025) into `data/raw/`. Data is not stored in git, so everyone runs it once.

Then open `notebooks/00_load_data.ipynb` and run all cells. The app runs with `streamlit run app/app.py`.

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

New to the sensors? Read [docs/MODIS_vs_VIIRS.md](docs/MODIS_vs_VIIRS.md) (what MODIS and VIIRS are, how they differ, and our harmonization plan; English + Arabic, with a one-page [PDF](docs/MODIS_vs_VIIRS.pdf)).

## Working together

Read [docs/TEAM_GUIDE.md](docs/TEAM_GUIDE.md) before your first commit.
