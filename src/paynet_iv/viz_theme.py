"""Matplotlib theme and palette for the transaction analysis notebook.

Kept out of the notebook so the notebook shows *analysis*, not rcParams. The
colour values are a validated palette: the categorical slots are assigned in a
fixed order (never cycled), the sequential ramp is a single hue, and the
diverging ramp is two poles around a neutral grey. Charts here are static
images, so the interactive hover layer an HTML chart would carry is replaced by
the printed summary table that accompanies each figure.
"""

from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------

# Categorical slots, in fixed assignment order. A chart that would need a 9th
# series folds the tail into "Other" instead of inventing a hue.
CATEGORICAL = [
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
]

# Scatter / all-pairs chart forms are capped at the first three slots, which are
# the ones that clear the colour-vision separation floors against every other
# member of the set rather than just their neighbours.
CATEGORICAL_ALL_PAIRS = CATEGORICAL[:3]

# Single-hue sequential ramp (blue), light -> dark, for continuous magnitude.
SEQUENTIAL = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]

# Reserved status colours. `critical` is what marks the fraud state -- it is a
# state, not a series, and it always ships with a label rather than relying on
# hue alone.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

# Chart chrome and ink, light surface.
INK = {
    "surface": "#fcfcfb",
    "page": "#f9f9f7",
    "primary": "#0b0b0b",
    "secondary": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
}

SEQ_CMAP = LinearSegmentedColormap.from_list("seq_blue", SEQUENTIAL)
# Diverging: two opposed poles with a neutral grey midpoint, equal arms.
DIV_CMAP = LinearSegmentedColormap.from_list(
    "div_blue_red", ["#184f95", "#3987e5", "#cde2fb", "#f0efec",
                     "#f6c9c9", "#e34948", "#a32424"]
)


def apply_theme() -> None:
    """Install the theme globally. Call once, near the top of the notebook."""
    mpl.rcParams.update({
        "figure.facecolor": INK["surface"],
        "axes.facecolor": INK["surface"],
        "savefig.facecolor": INK["surface"],
        "figure.dpi": 110,
        "savefig.dpi": 160,
        "savefig.bbox": "tight",

        "font.family": "DejaVu Sans",
        "font.size": 10,
        "text.color": INK["primary"],

        "axes.titlesize": 12.5,
        "axes.titleweight": "semibold",
        "axes.titlecolor": INK["primary"],
        "axes.titlelocation": "left",
        "axes.titlepad": 14,
        "axes.labelsize": 10,
        "axes.labelcolor": INK["secondary"],
        "axes.edgecolor": INK["axis"],
        "axes.linewidth": 0.8,
        # Recessive chrome: keep the baseline, drop the frame.
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.axisbelow": True,

        "grid.color": INK["grid"],
        "grid.linewidth": 0.8,

        "xtick.color": INK["muted"],
        "ytick.color": INK["muted"],
        "xtick.labelcolor": INK["secondary"],
        "ytick.labelcolor": INK["secondary"],
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "xtick.major.size": 0,
        "ytick.major.size": 0,

        "legend.frameon": False,
        "legend.fontsize": 9,
        "legend.labelcolor": INK["secondary"],

        "lines.linewidth": 2.0,
        "lines.markersize": 8,

        "axes.prop_cycle": mpl.cycler(color=CATEGORICAL),
    })


def subtitle(ax, text: str) -> None:
    """One line of context under the title, in secondary ink.

    Reads the title back from the *left* slot: the theme sets
    ``axes.titlelocation = "left"``, and a bare ``ax.get_title()`` reads the
    centre slot, which is empty -- re-setting from it silently erases the title.
    """
    current = ax.get_title(loc="left") or ax.get_title()
    ax.set_title(current, pad=26)
    ax.annotate(text, xy=(0, 1.0), xycoords="axes fraction",
                xytext=(0, 9), textcoords="offset points",
                ha="left", va="bottom", fontsize=9.5, color=INK["secondary"])


def label_bars(ax, bars, fmt="{:.2f}", horizontal=False, pad=4,
               only=None, color=None) -> None:
    """Direct-label bars. ``only`` restricts labelling to selected indices so
    the chart carries a few anchors rather than a number on every mark."""
    for i, b in enumerate(bars):
        if only is not None and i not in only:
            continue
        v = b.get_width() if horizontal else b.get_height()
        if horizontal:
            xy, off, ha, va = (b.get_width(), b.get_y() + b.get_height() / 2), (pad, 0), "left", "center"
        else:
            xy, off, ha, va = (b.get_x() + b.get_width() / 2, b.get_height()), (0, pad), "center", "bottom"
        ax.annotate(fmt.format(v), xy=xy, xytext=off, textcoords="offset points",
                    ha=ha, va=va, fontsize=9,
                    color=color or INK["secondary"])


def strip_x_grid(ax) -> None:
    ax.grid(False, axis="x")
    ax.grid(True, axis="y")


def horizontal_grid_only(ax) -> None:
    """For horizontal bar charts the useful grid runs the other way."""
    ax.grid(False, axis="y")
    ax.grid(True, axis="x")


def save(fig, name: str, outdir="../output/figures") -> None:
    import os
    os.makedirs(outdir, exist_ok=True)
    fig.savefig(f"{outdir}/{name}.png")


def stat_tiles(values, figsize=(11, 1.9)):
    """A KPI row. Some numbers are a headline, not a chart -- this is the form
    for a single magnitude with no comparison to draw."""
    fig, axes = plt.subplots(1, len(values), figsize=figsize)
    if len(values) == 1:
        axes = [axes]
    for ax, (label, value, note) in zip(axes, values):
        ax.axis("off")
        ax.text(0, 0.72, value, fontsize=23, color=INK["primary"],
                ha="left", va="center", fontweight="semibold")
        ax.text(0, 0.28, label, fontsize=9.5, color=INK["secondary"],
                ha="left", va="center")
        if note:
            ax.text(0, 0.03, note, fontsize=8.5, color=INK["muted"],
                    ha="left", va="center")
    fig.tight_layout()
    return fig
