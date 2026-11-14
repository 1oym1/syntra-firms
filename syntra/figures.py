"""Slide figures (PNG) for the harmonization, used by notebooks/01_harmonization.ipynb.

Colors: Okabe-Ito (colorblind-safe), the same as the app. Every series also has its own line style or
marker and a direct label, so color is never the only cue.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from syntra import fire_calendar as fc  # noqa: E402
from syntra import harmonize as hz  # noqa: E402

MODIS, VIIRS, HARM, GREY, INK = "#E69F00", "#56B4E9", "#009E73", "#9A9A9A", "#222222"
UNIT = "burned 0.1° cells"


def style():
    plt.rcParams.update({
        "figure.dpi": 100, "savefig.dpi": 200, "savefig.bbox": "tight", "font.size": 12,
        "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#BBBBBB",
        "axes.grid": True, "grid.color": "#E6E6E6", "grid.linewidth": 0.8, "axes.axisbelow": True,
        "axes.titlesize": 15, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "xtick.color": "#555555", "ytick.color": "#555555", "axes.labelcolor": "#444444",
        "legend.frameon": False,
    })


def _save(fig, path):
    if path is not None:
        fig.savefig(path, facecolor="white")
    return fig


def _annual(tab, col, first, last):
    t = tab[(tab.year >= first) & (tab.year <= last)]
    return t.groupby("year")[col].sum(min_count=1)


def raw_vs_harmonized(tab, country, path=None):
    """Yearly totals: raw MODIS, raw VIIRS, and the harmonized series (full years only)."""
    last = int(tab.loc[tab.month == 12, "year"].max())
    first = 2001
    modis = _annual(tab, "modis_consistent", first, last)
    viirs = _annual(tab[tab.viirs_flying], "viirs_cells", 2012, last)
    harm = _annual(tab, "harmonized_cells", first, last)
    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.plot(harm.index, harm.values, color=HARM, lw=3, label="Harmonized (VIIRS units)", zorder=3)
    ax.plot(modis.index, modis.values, color=MODIS, lw=2, ls="--", marker="o", ms=5, label="Raw MODIS")
    ax.plot(viirs.index, viirs.values, color=VIIRS, lw=2, ls=":", marker="s", ms=5, label="Raw VIIRS (S-NPP)")
    ax.axvline(2011.5, color=GREY, lw=1, ls="--")
    ax.text(2011.6, ax.get_ylim()[1] * 0.97, "VIIRS starts", va="top", color="#555555", fontsize=11)
    for ser, txt in ((harm, "Harmonized\n(= VIIRS from 2012)"), (modis, "Raw MODIS")):
        ax.annotate(txt, (ser.index[-1], ser.values[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", color=INK, fontsize=11, fontweight="bold")
    ax.set_xlim(first - 0.5, last + 4)
    ax.set_ylim(0, None)
    ax.set_ylabel(f"{UNIT} per year")
    ax.set_title(f"{country.replace('_', ' ')}: one fire record from two sensors, {first}–{last}")
    ax.legend(loc="lower left", ncol=3)
    return _save(fig, path)


def heldout_scatter(heldout, country, path=None):
    """Observed VIIRS vs raw MODIS and vs the held-out harmonized estimate, per month."""
    p = heldout["predictions"]
    fig, ax = plt.subplots(figsize=(6.4, 6.2))
    mx = float(max(p.viirs_cells.max(), p.pred.max())) * 1.05
    ax.plot([0, mx], [0, mx], color=GREY, lw=1.2, ls="--", label="perfect agreement")
    ax.scatter(p.viirs_cells, p.modis_consistent, s=36, color=MODIS, marker="o", edgecolor="white", lw=0.8,
               label=f"Raw MODIS (R² {heldout['r2_raw_modis']:.2f})")
    ax.scatter(p.viirs_cells, p.pred, s=40, color=HARM, marker="D", edgecolor="white", lw=0.8,
               label=f"Harmonized, held-out year (R² {heldout['r2']:.2f})")
    ax.set_xlim(0, mx)
    ax.set_ylim(0, mx)
    ax.set_xlabel(f"Observed VIIRS ({UNIT} per month)")
    ax.set_ylabel("Estimate from MODIS")
    ax.set_title(f"{country.replace('_', ' ')}: validation, {hz.OVERLAP[0]}–{hz.OVERLAP[1]}")
    ax.legend(loc="upper left")
    return _save(fig, path)


def calendar(series, country, path=None, cmap="Oranges"):
    """Year x month burning calendar of a monthly series (PeriodIndex)."""
    cal = fc.calendar(series)
    fig, ax = plt.subplots(figsize=(10, 0.32 * len(cal) + 1.6))
    im = ax.imshow(cal.values, aspect="auto", cmap=cmap, interpolation="nearest")
    ax.set_xticks(range(12), fc.MONTHS)
    ax.set_yticks(range(len(cal)), cal.index)
    ax.tick_params(axis="y", labelsize=9)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    if 2011 in cal.index and 2012 in cal.index:
        y = list(cal.index).index(2012) - 0.5
        ax.axhline(y, color=INK, lw=1.5, ls="--")
        ax.set_xlabel("Above the dashed line: MODIS converted to VIIRS units · below: VIIRS observed",
                      fontsize=10, labelpad=8)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.03)
    cb.set_label(f"{UNIT} per month")
    cb.outline.set_visible(False)
    ax.set_title(f"{country.replace('_', ' ')}: burning calendar {cal.index[0]}–{cal.index[-1]}")
    return _save(fig, path)


def month_bars(values, highlight, title, ylabel, path=None):
    """One bar per year (values: Series indexed by year), the highlighted year in green, median line."""
    hist = values.drop(highlight, errors="ignore")
    med = float(hist.median())
    fig, ax = plt.subplots(figsize=(10, 4.4))
    colors = [HARM if y == highlight else "#C9C9C9" for y in values.index]
    ax.bar(values.index, values.values, color=colors, width=0.75, edgecolor="white", linewidth=1)
    ax.axhline(med, color=INK, lw=1.2, ls="--")
    ax.text(values.index.min() - 0.4, med, f"median {med:,.0f}", va="bottom", fontsize=10, color=INK)
    if highlight in values.index:
        v = float(values[highlight])
        pct = 100 * (v - med) / med if med else np.nan
        ax.annotate(f"{highlight}: {v:,.0f}\n({pct:+.0f}% vs median)", (highlight, float(values.max())), xytext=(0, 6),
                    textcoords="offset points", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, float(values.max()) * 1.28)
    return _save(fig, path)


def factors(k_viirs, k_terra, country, path=None):
    """Monthly factors: MODIS -> VIIRS and Terra -> Terra+Aqua."""
    x = np.arange(12)
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.bar(x - 0.2, k_viirs.values, width=0.4, color=VIIRS, edgecolor="white", label="MODIS → VIIRS")
    ax.bar(x + 0.2, k_terra.values, width=0.4, color=MODIS, edgecolor="white", hatch="//",
           label="Terra → Terra+Aqua (2000–02 only)")
    ax.axhline(1, color=GREY, lw=1)
    ax.set_xticks(x, fc.MONTHS)
    ax.set_ylabel("factor (×)")
    ax.grid(axis="x", visible=False)
    ax.set_title(f"{country.replace('_', ' ')}: monthly conversion factors")
    ax.legend(loc="upper left")
    return _save(fig, path)


def validation_countries(table, path=None, floor=-1.0):
    """Held-out R², raw MODIS vs harmonized, per country (table = harmonization_validation.csv)."""
    t = table.copy()
    names = t.country.str.replace("_", " ")
    y = np.arange(len(t))[::-1]
    fig, ax = plt.subplots(figsize=(9, 0.9 * len(t) + 1.4))
    raw = t.r2_raw_modis.clip(lower=floor)
    ax.barh(y + 0.19, raw, height=0.36, color=MODIS, edgecolor="white", hatch="//", label="Raw MODIS")
    ax.barh(y - 0.19, t.r2_harmonized.clip(lower=floor), height=0.36, color=HARM, edgecolor="white",
            label="Harmonized")
    for yi, r, h in zip(y, t.r2_raw_modis, t.r2_harmonized):
        if r < floor:
            ax.text(floor + 0.03, yi + 0.19, f"{r:.1f} (bar cut)", va="center", ha="left", fontsize=10,
                    color=INK, fontweight="bold", bbox=dict(facecolor="white", edgecolor="none", pad=1.5))
        else:
            ax.text(r + (0.02 if r >= 0 else -0.02), yi + 0.19, f"{r:.2f}", va="center",
                    ha="left" if r >= 0 else "right", fontsize=10)
        ax.text(max(h, floor) + (0.02 if h >= 0 else -0.02), yi - 0.19, f"{h:.2f}", va="center",
                ha="left" if h >= 0 else "right", fontsize=10, fontweight="bold")
    ax.axvline(0, color=INK, lw=1)
    ax.set_yticks(y, names)
    ax.set_xlim(floor - 0.25, 1.15)
    ax.set_xlabel(f"R², monthly, leave-one-year-out {hz.OVERLAP[0]}–{hz.OVERLAP[1]}")
    ax.grid(axis="y", visible=False)
    ax.set_title("Harmonization skill by country")
    ax.legend(loc="lower right")
    return _save(fig, path)


def years_series(by_year):
    """Series indexed by int year (from series.month_to_date()['by_year'] or a calendar column)."""
    s = pd.Series(by_year).astype(float)
    s.index = s.index.astype(int)
    return s.sort_index()
