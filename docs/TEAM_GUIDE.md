# Team guide: working in this repo

We all work on each phase together, so the main risk is two people changing the same file at once. These habits avoid most problems.

## Every time you sit down

1. **Pull first.** In GitHub Desktop press **Fetch origin**, then **Pull origin**.
2. Make your change.
3. **Commit** with a short message that says what changed, for example `Add monthly median per sensor`.
4. **Push** right away so the others get it.

## Where does my file go?

| You made... | Put it in | Name it like |
| --- | --- | --- |
| A function others will reuse | `syntra/` (`data.py`, `harmonize.py`, ...) | `monthly_counts()` |
| Analysis for a phase | `notebooks/` | `01_harmonization.ipynb` (number = phase) |
| A quick experiment | `notebooks/scratch/` | `01_harmonization_obai.ipynb` |
| A chart for the slides | `outputs/figures/` | `fig_ratio_by_month.png` |
| A small result table | `outputs/tables/` | `ratio_by_month.csv` |
| App code | `app/` | |
| Slides, video | `presentation/` | |
| Method notes, decisions | `docs/` | |

If a notebook cell grows into something the app also needs, move it into `syntra/` and import it. One copy of the logic, never two.

## Branches

- `main` is the version that works. Do not push half-finished code there.
- For anything bigger than a small fix, make a branch: GitHub Desktop > Current branch > **New branch**, named after the task (`harmonization-ratio`, `app-calendar`).
- When it works, push the branch and open a **Pull request** on GitHub. Someone else glances at it and merges it.

## Notebooks

Two people editing the same `.ipynb` at once causes merge conflicts that are hard to fix. So:

- Say in WhatsApp which notebook you are editing.
- Experiment in your own copy under `notebooks/scratch/`, then move the working cells into the shared notebook.
- Clear big outputs before committing (Jupyter: Edit > Clear All Outputs).

## Data

Never commit the `data/` folder. Run `python scripts/fetch_firms.py` to get it. If you make a processed file others need, commit the code that makes it, not the file.
