# Team guide: working in this repo

We all work on each phase together, so the main risk is two people changing the same file at once. These few habits avoid most problems.

## Every time you sit down

1. **Pull first.** In GitHub Desktop press **Fetch origin**, then **Pull origin**.
2. Make your change.
3. **Commit** with a short message that says what changed, for example `Add monthly median per sensor`.
4. **Push** right away so the others get it.

## Branches

- `main` is the version that works. Do not push half-finished code there.
- For anything bigger than a small fix, make a branch: GitHub Desktop > Current branch > **New branch**, name it after the task (`harmonization-ratio`, `app-calendar`).
- When it works, push the branch and open a **Pull request** on GitHub. Someone else glances at it and merges it.

## Notebooks

Two people editing the same `.ipynb` at the same time causes merge conflicts that are hard to fix. So:

- Say in WhatsApp which notebook you are editing.
- Want to try something? Copy the notebook (`01_harmonization_obai.ipynb`), work there, then move the working cells into the shared one.
- Clear big outputs before committing (Jupyter: Edit > Clear All Outputs) to keep the repo small.

## Data

Never commit the `data/` folder. Run `python scripts/fetch_firms.py` to get it. If you make a processed file others need, write the code that makes it, not the file itself.

## Shared memory

Plans, questions and decisions go in the team's Claude Doc (Messages + Session log), same as the code goes here.
