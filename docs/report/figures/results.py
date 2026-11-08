"""Draw the held-out results figure for the report from the committed run.

Run from the repository root:

    uv run --group docs python docs/report/figures/results.py
"""

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

FIGURES = Path(__file__).resolve().parent
RUN = FIGURES.parents[2] / "eval" / "runs" / "20261108T135144Z"

ARMS = (
    ("model_alone", "A: model alone"),
    ("model_with_search", "B: model with search"),
    ("search_with_check", "C: search with check"),
    ("search_check_retry", "D: search, check and retry"),
)
PANELS = (
    ("correct", "(a) Correct, of 40 answerable", 40, 10),
    ("false_refusal", "(b) Answerable but declined", 40, 10),
    ("wrong", "(c) Wrong, of 50", 10, 2),
)


def read_counts(summary: Path) -> dict[tuple[str, str], list[int]]:
    """Map (arm, category) to its count in each run, in run order."""
    counts: dict[tuple[str, str], list[int]] = defaultdict(list)
    with summary.open(newline="", encoding="utf-8") as file:
        for row in sorted(csv.DictReader(file), key=lambda row: int(row["run"])):
            counts[row["arm"], row["category"]].append(int(row["count"]))
    return counts


def main() -> None:
    counts = read_counts(RUN / "summary.csv")
    plt.style.use(FIGURES / "laboratory.mplstyle")
    figure, axes_row = plt.subplots(1, len(PANELS), sharey=True, figsize=(6.89, 1.7))
    rows = range(len(ARMS))
    for axes, (category, title, limit, step) in zip(axes_row, PANELS, strict=True):
        runs = [counts[arm, category] for arm, _ in ARMS]
        means = [sum(values) / len(values) for values in runs]
        axes.hlines(
            rows,
            [min(v) for v in runs],
            [max(v) for v in runs],
            linewidth=2.4,
            color="#1F4A73",
        )
        axes.plot(means, rows, "o", color="#1A1A1A")
        axes.set_title(title)
        axes.set_xlim(0, limit)
        axes.set_xticks(range(0, limit + 1, step))
        axes.grid(axis="x", color="0.85", linewidth=0.5)
        axes.set_axisbelow(True)
    first = axes_row[0]
    first.set_yticks(rows, [label for _, label in ARMS])
    first.invert_yaxis()
    figure.savefig(FIGURES / "results.pdf", backend="pgf")


if __name__ == "__main__":
    main()
