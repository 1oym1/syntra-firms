# Status

Where the project stands. Newest first. Update it when something lands.


## 2026-11-14, about 14:00 (Hisham): app on PR #3's method, Sudan fully cleaned, figures

- **The app now uses `syntra/harmonize.py` (PR #3)**: burned 0.1° cells per month. See `docs/DECISIONS.md`.
  Fixed a bug in `harmonize_area` (drawn boxes lost years). 2026 + NOAA-20 + "this month so far" are in
  `syntra/series.py`.
- **Sudan fully cleaned** (`python -m syntra.pipeline --country Sudan`): 4,462,802 clean hotspots 2000 → 13 Nov 2026,
  4,417,341 vegetation fires; static 33,694 by type + 11,767 by the mask (700 cells); 543,545 API hotspots outside
  the border removed. Small result tables in `outputs/tables/` (`harmonized_Sudan.csv`, `run_info_Sudan.json`, ...).
- **Validation** (`scripts/validate_harmonization.py`, 2012–2021): R² Sudan 0.97, Ethiopia 0.98, Iraq 0.83,
  Saudi Arabia −0.75 (raw MODIS 0.39 / 0.55 / 0.34 / −20.7).
- **`notebooks/01_harmonization.ipynb`** + 7 slide figures in `outputs/figures/`.
- **Sudan results under this unit (provisional):** October 2026 is **normal** (1,545 vs median 1,540, #13 of 26).
  The "record October" in the 13:00 entry below came from the old unit and is **[OUTDATED]**.
  November 1–13: 1,412 vs median 1,592 (−11 %, #14 of 15).

**Still to do:** review + merge PR #1; Streamlit Cloud deploy (`FIRMS_MAP_KEY` in Secrets); 7 slides + 30 s video +
project page.

## [OUTDATED numbers: old unit] 2026-11-14, about 13:00 (Hisham): 2026 data + one cleaning step for everything (PR #1)

**2026 is in the app.** Data now runs to yesterday (13 Nov 2026), not Dec 2025.

- `syntra/recent.py` downloads 2026 from the FIRMS area API (MAP_KEY in `.env`, never committed) for MODIS,
  VIIRS S-NPP and VIIRS NOAA-20 and cleans them with **`syntra/clean.py`** (the team's Step 3), exactly like the
  archive, including the same Natural Earth 1:10m border clip (PR #2).
- `syntra/pipeline.py` is the whole chain for one country: fetch, clean, 2026, static mask, fire-cells.
  The app uses it.
- **Static-source mask on every year, not only 2026.** Tested: mask built from 2000–2024, applied to 2025.
  In Saudi Arabia 26 % of type-0 hotspots fall in static cells (flares FIRMS did not label); Sudan 0.16 %.
  Masking only 2026 would make 2026 look lower than history. A 1-cell margin around the mask was tested and
  rejected (doubles wrongly dropped vegetation fires).
- **S-NPP runs to 2 Nov 2026** (FIRMS availability list), so Jan–Oct 2026 is observed S-NPP. After that the app
  uses **NOAA-20 × 0.995**: 102 months both flew, held-out R² 0.996, bias 0.0 %.
- **MODIS Terra-only months (Nov 2000–Jun 2002)** scaled to Terra + Aqua (Riyadh's notebook, Part 4), now on our
  ~1 km fire-cell unit: factor about 2 per month, held-out R² 0.996.
- **"This month so far"**: Nov 1–13, 2026 compared with Nov 1–13 of every earlier year.
- Map: toggle to show static sources (Riyadh's Part 5a). Calendar and anomalies always use vegetation fires only.

**Sudan results (provisional, near-real-time):**
- **October 2026 = 20,403 fire-cells, highest October in 26 years (+72 % vs median 11,892)**, above the 90th
  percentile. Both VIIRS satellites agree (S-NPP 20,993, NOAA-20 20,617); MODIS is up 43 % on Oct 2025; the jump
  is in 16–31 Oct. Present it as an anomaly to check, not a confirmed record; possible causes are
  [TO CONFIRM].
- November 1–13, 2026: 13,702, −11 % vs median, #17 of 27 (normal).
- MODIS → VIIRS held-out R² is now 0.98 over 2012–2026 (178 months).

**Still to do:** review + merge PR #1; Streamlit Cloud deploy (put `FIRMS_MAP_KEY` in the app's secrets);
`notebooks/01_harmonization.ipynb` and slide figures; 7 slides + 30 s video + project page.

## 2026-11-14, about 12:00 (Hisham): harmonization + app, PR #1

**Team decision: Sudan is the main study area. We build on it first and may add a second country later (Ethiopia is ready); Saudi Arabia is the comparison case**. See `docs/DECISIONS.md`.

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
