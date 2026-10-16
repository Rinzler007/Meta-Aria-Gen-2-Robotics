#!/usr/bin/env python3
"""Collect every object pipeline run into one table and one figure.

The pipeline writes four files per recording and prints its numbers as it goes, which is
fine for one recording and useless for twelve. This reads the trajectories back off disk
and puts them side by side, so a claim about the object results is a claim about all of
them rather than about whichever one was run last.

    python3 tools/object_summary.py

It needs only the committed `outputs/object_*_trajectory.csv` files, so it runs on a fresh
clone with no recordings at all.
"""

import csv
import re
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "outputs"

# Each task gets its own colour so the figure can be read by task rather than by row and
# the order here is the order the recordings were made in.
TASKS = ["scoop", "pour", "pick", "grip"]
COLOURS = {"scoop": "#2C5F2D", "pour": "#065A82", "pick": "#B85042", "grip": "#6D2E46"}


def measures(p):
    """Read one trajectory file and reduce it to the handful of numbers worth comparing."""
    rows = list(csv.DictReader(p.open()))
    dev = np.array([[float(r["device_x"]), float(r["device_y"]), float(r["device_z"])] for r in rows])
    wld = np.array([[float(r["world_x"]), float(r["world_y"]), float(r["world_z"])] for r in rows])
    pts = np.array([int(r["n_points"]) for r in rows])

    def reduce(a):
        # Net displacement is where the object ended up relative to where it started. For
        # these tasks the two containers sit a fixed distance apart, so this is the one
        # quantity the task itself pins down and the one we can expect to repeat.
        net = np.linalg.norm(a[-1] - a[0]) * 100
        # Path length adds up every step, which also adds up every bit of per frame noise,
        # so it runs high and varies more. We keep it because it is the obvious measure
        # and showing that it varies is part of the point.
        path = np.linalg.norm(np.diff(a, axis=0), axis=1).sum() * 100
        # The diagonal of the box the object stayed inside depends only on the extremes,
        # so noise cannot accumulate in it the way it does in a path length.
        diag = np.linalg.norm(a.max(axis=0) - a.min(axis=0)) * 100
        return net, path, diag

    net_d, path_d, diag_d = reduce(dev)
    net_w, path_w, diag_w = reduce(wld)
    return dict(
        frames=len(rows), points=int(pts.sum()), points_min=int(pts.min()), points_max=int(pts.max()),
        net_dev_cm=net_d, net_room_cm=net_w,
        path_dev_cm=path_d, path_room_cm=path_w,
        diag_dev_cm=diag_d, diag_room_cm=diag_w,
    )


def main():
    files = sorted(OUT.glob("object_*_trajectory.csv"))
    if not files:
        raise SystemExit("no object trajectories in outputs/")

    # tools/object_head_motion.py writes this from the recordings. It is optional, since
    # a fresh clone has no recordings to compute it from and when it is there it answers
    # the question the rest of the table provokes.
    head = {}
    hm = OUT / "object_head_motion.csv"
    if hm.exists():
        head = {r["recording"]: r for r in csv.DictReader(hm.open())}

    rows = []
    for p in files:
        name = re.sub(r"^object_|_trajectory\.csv$", "", p.name)
        task = name.rsplit("_", 1)[0]
        r = dict(recording=name, task=task, **measures(p))
        h = head.get(name)
        # Without the head figures we still write the columns, empty, so the file keeps
        # one shape whether or not somebody had the recordings to hand.
        r["head_net_cm"] = float(h["head_net_cm"]) if h else ""
        r["head_path_cm"] = float(h["head_path_cm"]) if h else ""
        rows.append(r)
    # Sort by the task order we record in rather than alphabetically, so the table reads
    # in the order someone watching the footage would meet them.
    rows.sort(key=lambda r: (TASKS.index(r["task"]) if r["task"] in TASKS else 99, r["recording"]))

    csv_path = OUT / "object_summary.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # The figure answers the one question the table is bad at: does the room frame
    # correction behave the same way for an object as it did for the wrist ?
    fig, axes = plt.subplots(1, 2, figsize=(13, 0.45 * len(rows) + 2.6))
    y = np.arange(len(rows))[::-1]

    for ax, (key_d, key_w, title) in zip(axes, [
        ("net_dev_cm", "net_room_cm", "Net displacement, start to finish"),
        ("diag_dev_cm", "diag_room_cm", "Diagonal of the box the object stayed inside"),
    ]):
        for i, r in zip(y, rows):
            c = COLOURS.get(r["task"], "#36454F")
            ax.plot([r[key_d], r[key_w]], [i, i], color="#BBBBBB", lw=2, zorder=1)
            ax.scatter(r[key_d], i, s=46, color=c, zorder=2)
            ax.scatter(r[key_w], i, s=46, color=c, zorder=2, facecolors="none", linewidths=1.8)
        ax.set_yticks(y)
        ax.set_yticklabels([r["recording"] for r in rows], fontsize=9)
        ax.set_xlabel("centimetres")
        ax.set_title(title, fontsize=11)
        ax.grid(axis="x", color="#EEEEEE")
        ax.set_axisbelow(True)

    # Filled is what the glasses record, hollow is the same thing measured against the
    # room. We say so once rather than on both panels.
    axes[0].scatter([], [], s=46, color="#36454F", label="relative to the glasses")
    axes[0].scatter([], [], s=46, facecolors="none", edgecolors="#36454F", linewidths=1.8,
                    label="relative to the room")
    axes[0].legend(loc="lower right", fontsize=9, frameon=False)

    fig.suptitle("Object trajectories across the October recordings", fontsize=13)
    fig.tight_layout()
    png = OUT / "object_summary.png"
    fig.savefig(png, dpi=150)

    # Print the table so a run of this script is also a readable report, not only two
    # files appearing in outputs/.
    print(f"{'recording':<12} {'frames':>6} {'points':>9} {'net dev':>8} {'net room':>9} "
          f"{'diag dev':>9} {'diag room':>10} {'ratio':>6} {'head':>6}")
    for r in rows:
        # The ratio is here because it is the first thing anyone asks for, having seen it
        # work for the wrist. The head column sits next to it because the two have to be
        # read together: see the note printed underneath.
        ratio = r["net_room_cm"] / r["net_dev_cm"] if r["net_dev_cm"] else float("nan")
        h = f"{r['head_net_cm']:.1f}" if r["head_net_cm"] != "" else "-"
        print(f"{r['recording']:<12} {r['frames']:>6} {r['points']:>9,} "
              f"{r['net_dev_cm']:>7.1f}  {r['net_room_cm']:>8.1f} "
              f"{r['diag_dev_cm']:>8.1f}  {r['diag_room_cm']:>9.1f} "
              f"{ratio:>6.2f} {h:>6}")

    # A spread across takes of the same task is the thing we can actually defend, so we
    # work it out here rather than leaving it to be eyeballed off the table.
    print()
    for task in TASKS:
        t = [r for r in rows if r["task"] == task]
        if len(t) < 2:
            continue
        v = np.array([r["net_room_cm"] for r in t])
        print(f"{task:<6} net displacement in the room frame: "
              f"{', '.join(f'{x:.1f}' for x in v)} cm, "
              f"mean {v.mean():.1f}, spread {(v.max() - v.min()) / v.mean() * 100:.0f}%")

    if any(r["head_net_cm"] != "" for r in rows):
        hn = np.array([r["head_net_cm"] for r in rows if r["head_net_cm"] != ""])
        print(f"\nThe head moved {hn.min():.1f} to {hn.max():.1f} cm during these windows. That is why the")
        print("ratio column swings while the wrist ratio does not. Your hand and your head are")
        print("attached to each other, so the head follows the hand and the difference between")
        print("them stays small. An object on a table is under no such obligation, so head")
        print("movement enters the glasses frame measurement on its own and the room frame")
        print("correction can as easily shrink the movement as grow it.")

    print(f"\nwrote {csv_path.relative_to(REPO)} and {png.relative_to(REPO)}")


if __name__ == "__main__":
    main()
