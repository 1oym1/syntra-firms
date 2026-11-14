# Status

Where the project stands. Newest first. Update it when something lands.

## 2026-11-14, about 12:00 (Hisham): harmonization + app, PR #1

**Team decision: Sudan is the main study area** (backup Ethiopia; Saudi Arabia as the comparison case). See `docs/DECISIONS.md`.

**Pull request:** [#1 Harmonization (phases 4-5) + full Streamlit app](https://github.com/1oym1/syntra-firms/pull/1). Needs a review and a merge.

### Done in PR #1

1. **Harmonization (phase 4)**, `syntra/harmonize.py`
   - Keep confidence nominal/high only (MODIS ≥ 30 ≙ VIIRS n/h). Type 0 only, as in `load_fires`.
   - Snap every hotspot to a 0.01° (~1 km) grid and count unique fire-cells per day.
   - On the 2012–2025 overlap, fit `VIIRS = a(month) + b × MODIS` (MODIS vs VIIRS S-NPP).
   - Before 2012 use MODIS converted to VIIRS-equivalent; from 2012 use observed VIIRS.
2. **Validation (phase 5)**, `scripts/validate_harmonization.py` → `outputs/tables/harmonization_validation.csv`.
   Leave-one-year-out: each year 2012–2025 is predicted by a model that never saw it (168 months per country).

   | Country | R² raw MODIS | R² seasonal ratio | **R² our model** | Bias (model) |
   | --- | --- | --- | --- | --- |
   | Sudan | 0.31 | 0.99 | **0.99** | −0.1 % |
   | Ethiopia | 0.21 | 0.97 | **0.97** | 0.0 % |
   | Iraq | −0.27 | 0.71 | **0.88** | +0.2 % |
   | Saudi Arabia | −11.0 | −0.71 | **0.28** | +0.1 % |

   This confirms the Sudan recommendation over 14 years, not only 2025. Saudi Arabia (few, scattered fires) is
   the "limits of the method" example.
3. **App**, `app/app.py` (replaces the placeholder)
   - Country picker (Sudan by default, or any FIRMS country name).
   - Area: whole country, **draw a rectangle on the map**, or type lat/lon.
   - Harmonized year × month burning calendar, colorblind-safe ramps.
   - Selected month vs historical median, with rank and a 90th-percentile alert.
   - Raw vs harmonized charts and the validation table.
   - Hotspot map.
   - CSV downloads: monthly series, calendar, hotspots.
4. **Data**: `syntra/data.py` downloads in parallel (about 1 minute per country) and takes an optional `instruments=`.

Try it:

```bash
pip install -r requirements.txt
streamlit run app/app.py
python scripts/validate_harmonization.py --countries Sudan Ethiopia
```

### Still to do

- [ ] Review and merge PR #1
- [ ] 2026 data: Suomi NPP stopped on 2 Nov 2026, so this year needs NOAA-20 from the FIRMS API (free MAP_KEY)
      plus a NOAA-20 → S-NPP calibration on the 2018–2025 overlap
- [ ] `notebooks/01_harmonization.ipynb` and slide figures in `outputs/figures/`
- [ ] Deploy on Streamlit Community Cloud (live link for the judges)
- [ ] 7 slides + 30-second video, project page text in English (summary, NASA data used, AI tools used, references)

### Deadlines

- **Sun 15 Nov, 12:00 noon**: local judging submission (AOU Jeddah)
- Sun 15 Nov, 23:59: spaceappschallenge.org closes
