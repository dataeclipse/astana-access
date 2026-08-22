from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

from astana_access.config import FIGURES

RC = {
    "figure.figsize": (6.3, 4.2),
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "axes.grid": True,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.5,
    "legend.frameon": False,
    "legend.fontsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "ps.useafm": True,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
}


def apply() -> None:
    mpl.rcParams.update(RC)


def save(fig: plt.Figure, name: str, directory: Path | None = None) -> list[Path]:
    target = directory or FIGURES
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for suffix in (".eps", ".pdf"):
        path = target / f"{name}{suffix}"
        fig.savefig(path)
        written.append(path)
    plt.close(fig)
    return written
