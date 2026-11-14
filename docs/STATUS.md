# Status

Where the project stands. Newest first. Update it when something lands.




## 2026-11-14, about 18:30 (Hisham): thresholds written down, Jan 2012 fixed everywhere, faster first load

- **Status and risk thresholds are written down**: in the app ("How the status is decided" under the status card,
  and the caption under the risk chart) and in `docs/DECISIONS.md`. Very high = above the 90th percentile of the
  same calendar month; Above / Below normal = at least 20 % above / below the median; risk classes by the share of
  years a week was high (≥ 75 % Extreme, ≥ 50 % High, ≥ 25 % Moderate). These are choices, not physics
  **[TO CONFIRM with the team]**.
- **Sensor switches**: the map tab now says the sensor and static-source switches change only the map, the counts
  above it and the hotspot CSV. Calendar, status, trends, risk and 3D always use the harmonized record of all
  sensors (sidebar "Calendar shows → Raw MODIS / Raw VIIRS" for one sensor's raw counts).
- **January 2012, done everywhere**: the sensor start months now live in one place, `clean.SENSOR_START`
  (VIIRS from Feb 2012), used by `harmonize.py`, `series.py` and the app. `harmonize.run("Sudan")` now gives the
  app's numbers: held-out R² 0.993, RMSE 301. (The Riyadh item in the 18:00 entry is done.) Also fixed a crash in
  `harmonize.run` when the FIRMS API adds no new year.
- **Faster load**: this year's FIRMS API data is cleaned once and cached on disk for 3 h
  (`data/processed/cache/nrt_<country>_<year>.parquet`, git-ignored with `data/`). Sudan: 44 s → 6 s; cold start
  of the whole app about 27 s. A country opened for the first time still downloads its yearly archive files
  (measured: Ethiopia 334 s, Iraq 246 s, Saudi Arabia 239 s), so before the demo run `python scripts/warm_cache.py`
  (Sudan, Ethiopia, Saudi Arabia, Iraq; done 14 Nov). The archive stays on disk; after 3 h only this year's data is
  fetched again (about 35 s).

## 2026-11-14, about 18:00 (Hisham): risk periods tab; January 2012 fix

- **⚠️ Risk periods** (Yazeed's question 2: which periods historically carry the greatest fire risk). Per week of
  the year, from every full year: how often the week had high activity (above a percentile of all weeks, default
  75th, adjustable), typical and bad-year values, classed Low / Moderate / High / Extreme; a years × weeks ranking
  heatmap; and the fire season per year (first to last high week, fire years start at the quietest week so the
  Oct–Mar season stays whole). Sudan: **22 Oct – 23 Dec is Extreme (high activity in 97 % of years)**; the number
  of high-activity weeks grows **+3.1 weeks per decade** (linear fit, a direction only).
- **Fix, January 2012:** VIIRS S-NPP data in FIRMS starts on **20 Jan 2012**, so Jan 2012 was a part month
  counted as full VIIRS (Sudan: 1,523 instead of ~4,069). `syntra/series.py` now starts VIIRS in Feb 2012; Jan 2012
  is MODIS × factor and is left out of the fit. Sudan held-out R² 0.988 → **0.993**, RMSE 393 → 301, R² on
  anomalies 0.79 → 0.87. Oct 2026 and Nov 1–13 unchanged.
- [DONE 18:30] **[TO CONFIRM with Riyadh]** `syntra/harmonize.py` (`harmonize.run`, `scripts/harmonize_hotspots.py`) still
  counts Jan 2012 as a VIIRS month, so its validation numbers differ slightly from the app's. Same one-line fix
  there (VIIRS span from Feb 2012) would make them match.

## 2026-11-14, about 17:30 (Hisham): app redesign, 3D views, FR gaps closed

- New look: dark theme (`.streamlit/config.toml`), hero header with live-data pill, plain-language status card
  (🔴 Very high / 🟠 Above normal / 🟢 Normal / 🔵 Below normal, icon + word + color), "what next month usually
  brings" card (climatology, not a forecast).
- KPIs (FR14): month vs median, Jan–month total vs median, busiest month on record, busiest full year.
- 🧊 3D view: rotatable "fire landscape" (years × months × fire cell-days; raw shows the 2012 cliff, harmonized
  removes it) and "regions over time" (Yazeed's spec: fires per week over time for 2–3 regions; split N→S or W→E,
  2/3 regions, week/month, years, smoothing, compare shapes are all settings).
- 📈 Trend & the 2012 jump (FR12): raw stitched record jumps ×2.5 in 2012 (Sudan), harmonized ×0.99; linear trend
  +6 %/decade (fit R² 0.06, so a direction only). Fire-season clock (polar) in the calendar tab.
- Map (Hisham's list): live last 7 days / selected month / custom dates; MODIS, VIIRS S-NPP, VIIRS NOAA-20 on/off;
  static sources on/off (shows what cleaning removed); density view.
- Download (FR16): one interactive HTML report with the status text and every chart.
- `.streamlit/secrets.toml` added to `.gitignore`.
- Checked: browser at desktop and phone width; headless test of the default page. The headless test cannot drive
  `st.pills` (a Streamlit testing limit), so the sensor toggles were checked by hand in the browser.

## 2026-11-14, about 16:30 (Hisham): main's PR #5 merged into PR #1, unit is now cell-days

- PR #5 (Riyadh/it3x) changed `syntra/harmonize.py` to count **fire cell-days per month** (each 0.1° cell once per
  day) instead of burned cells per month. Merged into `hisham/harmonization-app`; kept the `spans` argument the app
  needs. `syntra/series.py` (NOAA-20 factor, "this month so far") now uses the same count, so the app, notebook
  and `harmonize.run` agree. App labels say "fire cell-days".
- **New Sudan numbers (replace the 14:00/15:00 ones):** held-out R² **0.988** (raw MODIS 0.36), RMSE 393 cell-days,
  R² on anomalies 0.79, median annual error 2.4 %. NOAA-20 k = 0.986 (held-out R² 0.997).
  **October 2026 = 7,753 cell-days, +56 % vs median 4,966, #2 of 26** (a big October again: under the old unit the
  extra fires burned in cells that were already burning, so they did not show).
  Nov 1–13: +0.3 % vs median, #8 of 15 (normal). Darfur box (22–26E, 10–14N): Oct +29 %, Nov 1–13 +25 % (#3 of 15).
- 4-country validation rerun (README table): Sudan 0.99, Ethiopia 0.97, Iraq 0.91, Saudi −0.87.
- **Still on the old unit [TO UPDATE]:** figures 01–07 (`notebooks/01_harmonization.ipynb`) and the WhatsApp
  update posted 13:47 ("October 2026 normal" is now wrong). Step 3 (`compare.py`, figures 08–11) is a sensor
  comparison and stays as it is.
## 2026-11-14, about 15:00 (Hisham): one 2026 loader, Riyadh's `syntra/nrt.py`

- The app and `syntra/pipeline.py` now get 2026 from `syntra/nrt.py` (PR #4). `syntra/recent.py` is deleted, so there
  is one copy of the 2026 logic. On top of nrt the app still converts NOAA-20 to S-NPP units (× 0.992) after S-NPP's
  last day; `harmonize.run` uses raw NOAA-20 there. The difference is 0.8 % for Nov 3 on.
- [OUTDATED numbers: old unit, see 16:30] Same Sudan results as before: 4,462,802 clean rows, held-out R² 0.975, Oct 2026 1,545 (normal), Nov 1–13 −11 %.
- `python -m syntra.pipeline` writes `clean_vegetation_<country>.csv` as MODIS + one VIIRS per day (nrt's rule), so
  `python -m syntra.harmonize` reads it correctly.
## 2026-11-14, about 14:30 (Hisham): checklist step 3, MODIS vs VIIRS on clean data

Riyadh's checklist: 1 download ✅ → 2 clean ✅ → **3 handle the difference ✅** → 4 aggregate monthly ✅ → 5 app ✅ (deploy still to do).
`notebooks/02_modis_vs_viirs.ipynb` + `syntra/compare.py`, figures 08–11, tables `outputs/tables/sensor_*_Sudan.csv`.
Sudan 2012–2025: hotspots ×4.1 vs burned cells ×1.9 (resolution; one VIIRS satellite vs both MODIS satellites);
same pass, VIIRS sees 93 % of MODIS's fire cells, MODIS 67 % of VIIRS's, extra VIIRS fires are small (sensitivity);
the gap is ×1.4 in Nov, ×6.8 in Jul (per-month factor).
**Checked (Hisham, 15:30):** counts recomputed independently from the clean files: identical. The first same-pass
figure (71 % / 22 %) was **[OUTDATED]**: it counted Aqua swath gaps and next-cell fires as misses. Corrected test above.
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
