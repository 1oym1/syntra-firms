# SYNTRA | MODIS + VIIRS Fire Hotspot Harmonization

Team SYNTRA's project for the **NASA Space Apps Challenge 2026** (Jeddah), challenge [Harmonization of MODIS and VIIRS Hot Spots](https://www.spaceappschallenge.org/2026/challenges/modis-and-viirs-hot-spots/).

Satellites have recorded fire hotspots since 2000, but the record is split between two sensors: MODIS (about 1 km pixels, 2000 to now) and VIIRS (about 375 m pixels, 2012 to now). Their counts cannot be compared directly. We merge them into one consistent record and show it as a burning-activity calendar for an area the user picks.

## Team

Riyadh Barnawi (team owner), Yazeed Firas, Obai Merdad, Ahmad Qadah, Hisham Albaiti.

## Quick start

```bash
git clone <repo url>
cd syntra-firms
pip install -r requirements.txt
python scripts/fetch_firms.py
```

`fetch_firms.py` downloads the FIRMS yearly files (Saudi Arabia, 2000 to 2025 by default) into `data/raw/`. The data folder is not stored in git, so every member downloads it once with this command.

Then open `notebooks/00_starter_load_firms_data.ipynb` in VS Code or Jupyter and run all cells.

## Folders

| Folder | What goes there |
| --- | --- |
| `notebooks/` | Analysis notebooks, numbered by workflow phase |
| `scripts/` | Command-line helpers (data download) |
| `data/raw/` | FIRMS files as downloaded (not in git) |
| `data/processed/` | Cleaned and merged tables (not in git) |
| `docs/` | Team guide and method notes |

## Data

[NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) active fire data: MODIS Collection 6.1 and VIIRS 375 m (Suomi NPP and NOAA-20). Column meanings: [FIRMS attribute definitions](https://www.earthdata.nasa.gov/data/tools/firms/active-fire-data-attributes-modis-viirs).

## Working together

See [docs/TEAM_GUIDE.md](docs/TEAM_GUIDE.md) for how we use branches, pulls and commits.
