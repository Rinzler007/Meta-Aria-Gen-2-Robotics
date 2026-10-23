#!/usr/bin/env python3
"""Choose the window for each recording from the grip detection, with no hand picking.

The pipeline works on a window of a recording. Until now a person watched each clip and
chose four seconds of it. That is one of the two manual steps left, and it is the one that
stops the three takes of a task being comparable, since four seconds picked for one take
need not sit at the same point in the task as four seconds picked for the next.

`tools/grasp_intervals.py` now finds when the hand takes hold of something and when it
lets go, across all twelve recordings. The demonstration is what happens between those two
moments, so the window can come straight from them.

What it proposes. The whole hold, trimmed slightly at each end. The trim is there because
the hand is still closing at the start of a hold and already opening at the end, so the
object is poorly placed in those frames.

    python3 tools/auto_window.py              # compare against the hand picked windows
    python3 tools/auto_window.py --write      # write the proposals into object_runs.csv

One thing it cannot do for you. The prompt is a pixel coordinate on the object in the
window's first frame, so moving a window invalidates its prompt. `tools/find_prompt.py`
has to run again for any recording whose window changes, and somebody still has to look at
the contact sheet. Automating the window does not automate the coordinate.
"""

import argparse
import csv
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "outputs"
RUNS = REPO / "tools" / "object_runs.csv"

# The hand is still closing at the start of a hold and already opening at the end, so the
# object sits awkwardly in those frames. Trimming both ends keeps the settled middle.
TRIM_S = 0.6

# Shorter than this is not a demonstration of anything.
MIN_WINDOW_S = 2.0


def proposals():
    """One window per recording, taken from where the hand was holding something."""
    src = OUT / "grasp_intervals.csv"
    if not src.exists():
        raise SystemExit("run tools/grasp_intervals.py first")
    out = {}
    for r in csv.DictReader(src.open()):
        if r["separable"] != "yes" or not r["held_from_s"]:
            continue
        a = float(r["held_from_s"]) + TRIM_S
        b = float(r["held_to_s"]) - TRIM_S
        if b - a >= MIN_WINDOW_S:
            out[r["recording"]] = (a, b)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="write the proposals into tools/object_runs.csv")
    a = ap.parse_args()

    prop = proposals()
    rows = list(csv.DictReader(RUNS.open()))

    print(f"{'recording':<10} {'chosen by hand':>16} {'proposed':>18} {'length':>7}  overlap")
    kept = 0
    for r in rows:
        name = r.get("label") or r["recording"]
        if name not in prop:
            continue
        p0, p1 = prop[name]
        h0, h1 = float(r["start_s"]), float(r["start_s"]) + 4.0
        # How much of the window a person chose falls inside the one proposed here. The
        # hand picked windows were settled before any of this existed, so they owe the
        # proposal nothing.
        over = max(0.0, min(p1, h1) - max(p0, h0)) / (h1 - h0)
        kept += over
        print(f"{name:<10} {f'{h0:5.2f} to {h1:5.2f}':>16} {f'{p0:5.2f} to {p1:5.2f}':>18} "
              f"{p1 - p0:6.1f} s  {over:4.0%}")
    print(f"\nproposals cover {kept / len(prop):.0%} of the windows chosen by hand, "
          f"across {len(prop)} recordings")

    if not a.write:
        print("\nNothing written. Pass --write to put these into tools/object_runs.csv, then")
        print("re-run tools/find_prompt.py for each one, because the prompt moves with the window.")
        return

    fields = list(rows[0])
    if "duration_s" not in fields:
        fields.insert(fields.index("start_s") + 1, "duration_s")
    for r in rows:
        name = r.get("label") or r["recording"]
        r.setdefault("duration_s", "4.0")
        if name in prop:
            r["start_s"] = f"{prop[name][0]:.2f}"
            r["duration_s"] = f"{prop[name][1] - prop[name][0]:.2f}"
    with RUNS.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {len(prop)} window starts into {RUNS.name}. The prompts are now stale.")


if __name__ == "__main__":
    main()
