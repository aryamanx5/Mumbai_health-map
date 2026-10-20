"""Shared matplotlib styling (reference data-viz palette, light surface)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIVERGING = ("#2a78d6", "#f0efec", "#e34948")  # negative (blue) - neutral - positive (red)
NEUTRAL = "#a3a29c"
MARKERS = ["o", "s", "^", "D", "v", "P"]
CATEGORY_LABELS = {"dispensary": "Dispensary", "uphc": "UPHC", "public_hospital": "Public hospital",
                   "maternity_hospital": "Maternity home"}
CATEGORY_COLORS = dict(zip(CATEGORY_LABELS, SERIES))


def apply():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": TEXT_2, "xtick.color": TEXT_2, "ytick.color": TEXT_2,
        "text.color": TEXT, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold",
        "axes.titlesize": 12, "axes.titlelocation": "left", "axes.labelsize": 10, "font.size": 10,
        "legend.frameon": False, "figure.dpi": 110, "savefig.dpi": 160, "savefig.bbox": "tight",
    })


def note(fig, text):
    fig.text(0.01, -0.02, text, ha="left", va="top", fontsize=8, color=TEXT_2, wrap=True)
