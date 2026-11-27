"""Plot caller repos per reusable workflow from docs/img/callers.csv."""
import csv
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from plot_style import save  # noqa: E402

with open(HERE / "callers.csv") as handle:
    data = {row["workflow"]: int(row["caller_repos"]) for row in csv.DictReader(handle)}


def draw(fig, theme, data):
    ax = fig.subplots()
    names = list(data)[::-1]
    values = [data[n] for n in names]
    bars = ax.barh(names, values, color=theme["series"][0])
    ax.bar_label(bars, padding=3, color=theme["text"], fontsize=8)
    ax.set_xlabel("OpenVoiceOS repos that call the workflow")
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(axis="y", visible=False)


save(str(HERE / "callers"), draw, data, height=0.22 * len(data) + 1.0)
