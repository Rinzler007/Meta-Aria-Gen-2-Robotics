#!/usr/bin/env python3
"""Do the three takes of a task produce the same measurement ?

This is the question the recordings were made to answer. Each task was performed three
times, so a number that means anything should come out roughly the same on all three. A
number that swings wildly across takes is telling you about the method and not about the
task.

Two measures are compared, because they behave very differently once a window covers a
whole demonstration.

Net displacement is where the object finished against where it started. It suits a window
cut from the middle of a carry. It is close to useless across a whole demonstration,
because somebody who picks a spoon up, scoops with it and puts it back has moved it almost
nowhere, so the figure collapses towards zero and the spread blows up.

The box diagonal is the size of the smallest box the object stayed inside. It measures how
much space the demonstration swept out, which is a property of the task, so it survives the
object returning to where it began.

    python3 tools/repeatability.py

It reads `outputs/object_summary.csv` and writes `outputs/repeatability.csv`. Run
`tools/object_summary.py` first. Objects tracked as a second thing from one recording, for
eg. `scoop_01_bowl`, are left out, since they are not takes of a task.
"""

import csv
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "outputs"
TASKS = ["scoop", "pour", "pick", "grip"]


def spread(values):
    """How far apart the takes are, as a share of their average."""
    v = np.asarray(values, dtype=float)
    return float((v.max() - v.min()) / v.mean() * 100) if v.mean() else float("nan")


def main():
    src = OUT / "object_summary.csv"
    if not src.exists():
        raise SystemExit("run tools/object_summary.py first")

    # One underscore means a take of a task. Two means a second object from the same
    # recording, which is not a take and does not belong in this comparison.
    rows = [r for r in csv.DictReader(src.open()) if r["recording"].count("_") == 1]

    out = []
    print(f"{'task':<7} {'takes':>5} {'net displacement':>32} {'box diagonal':>32}")
    print(f"{'':<7} {'':>5} {'values (cm)':>22} {'spread':>9} {'values (cm)':>22} {'spread':>9}")
    for task in TASKS:
        sel = [r for r in rows if r["task"] == task]
        if len(sel) < 2:
            continue
        net = [float(r["net_room_cm"]) for r in sel]
        box = [float(r["diag_room_cm"]) for r in sel]
        out.append(dict(task=task, takes=len(sel),
                        net_values_cm=" ".join(f"{v:.1f}" for v in net),
                        net_spread_pct=round(spread(net)),
                        box_values_cm=" ".join(f"{v:.1f}" for v in box),
                        box_spread_pct=round(spread(box))))
        print(f"{task:<7} {len(sel):>5} {' '.join(f'{v:5.1f}' for v in net):>22} "
              f"{spread(net):8.0f}% {' '.join(f'{v:5.1f}' for v in box):>22} {spread(box):8.0f}%")

    dest = OUT / "repeatability.csv"
    with dest.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)

    print()
    print("Lower spread means the three takes agree better. Read the box diagonal column")
    print("when the windows cover whole demonstrations, since net displacement goes to zero")
    print("whenever an object is returned to where it started.")
    print(f"\nwrote {dest.relative_to(REPO)}")


if __name__ == "__main__":
    main()
