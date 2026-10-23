#!/usr/bin/env python3
"""Draw the SE(3) pose of the object, so the 4 by 4 matrices can actually be looked at.

`tools/object_pose.py` writes one 4 by 4 matrix per frame into
`outputs/object_<label>_pose.csv`. A csv of sixteen numbers per row is the right thing to
hand to a robot and the wrong thing to put in front of a person. This draws it.

    python3 tools/render_pose.py                 # every recording
    python3 tools/render_pose.py pour_02         # just this one
    python3 tools/render_pose.py --row           # one row, for a slide
    python3 tools/render_pose.py --formula       # just the algebra, drawn as a picture

The default is a two by two grid, which is the shape to read on a screen or in a report.
A slide gives you a wide strip under the text, so `--row` puts the same four panels in a
single row and writes them beside the grid as `_pose_row.png`.

`--formula` writes `outputs/se3_formula.png`, which is the matrix and the four pieces of
algebra drawn out. A formula typed into a slide as a line of words is hard to read and easy
to get wrong, so it is drawn here once and the slide uses the picture.

What the pose is. A rigid body in a room has a position and a facing. A 4 by 4 matrix
holds both:

    T = [ R  t ]     R is 3 by 3 and says which way the object is turned
        [ 0  1 ]     t is 3 by 1 and says where it is

Why that shape. Writing a point as four numbers ending in 1 makes the turn and the shift
into a single multiplication, `p' = T p`, so a chain of movements is a product of matrices
and undoing one is an inverse. Both of those are what you need to move a measurement
between frames of reference.

What is drawn, in four panels.

**How far it has turned** is the angle of the rotation since the window's first frame, in
degrees. One number out of nine, taken from the trace, because a rotation turns by a
definite amount whatever axis it turns about.

**Which way it has turned** is the axis of that rotation, as the three components of a unit
vector. A flat line means the object kept turning about the same axis, which is what
pouring from a jug looks like. Scribble means the turn is too small for its axis to mean
anything, since an axis is undefined at zero rotation.

**Where it has moved** is the translation, the three components of t, in centimetres.

**The matrix itself** is printed at the start, the middle and the end of the window, so the
numbers a robot would read are on the page next to the curves that describe them.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "outputs"



def formula(dest):
    """Draw the algebra, so a slide can show a matrix as a matrix.

    Matplotlib's maths renderer has no matrix environment, so the brackets and the blocks
    inside them are drawn by hand. That is a few more lines here and it means the picture
    is built by this repository like every other figure, which is the point.

    The labels sit inside the cells they describe. Arrows pointing in from outside were
    tried and they cross the brackets, which makes a picture of a matrix harder to read
    than the matrix.
    """
    fig = plt.figure(figsize=(16, 5.4))
    BLUE, RED, GREY = "#1C7293", "#B85042", "#808080"

    # ---- the matrix itself, on the left -------------------------------------------
    ax = fig.add_axes([0.02, 0.04, 0.40, 0.92])
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")

    ax.text(0.5, 5.0, r"$T$", fontsize=46, va="center", ha="center")
    ax.text(1.6, 5.0, r"$=$", fontsize=36, va="center", ha="center")

    # The square brackets. Three strokes each, drawn in axis coordinates so they scale
    # with the figure. Tying them to a font would break the moment the size changed.
    for x, side in ((2.5, 1), (9.7, -1)):
        ax.plot([x, x], [0.9, 9.1], color="black", lw=2.6)
        ax.plot([x, x + 0.32 * side], [9.1, 9.1], color="black", lw=2.6)
        ax.plot([x, x + 0.32 * side], [0.9, 0.9], color="black", lw=2.6)

    # A faint rule between the blocks, which is how a 3 by 3 and a 3 by 1 are usually shown
    # apart without claiming they are two separate matrices.
    ax.plot([6.45, 6.45], [1.3, 8.7], color="#CCCCCC", lw=1, ls=(0, (4, 4)))
    ax.plot([2.8, 9.4], [3.3, 3.3], color="#CCCCCC", lw=1, ls=(0, (4, 4)))

    ax.text(4.6, 7.0, r"$R$", fontsize=40, va="center", ha="center", color=BLUE)
    ax.text(4.6, 5.3, "rotation, 3 by 3\nwhich way it is turned",
            fontsize=12, va="center", ha="center", color=BLUE)
    ax.text(8.1, 7.0, r"$t$", fontsize=40, va="center", ha="center", color=RED)
    ax.text(8.1, 5.3, "translation, 3 by 1\nwhere it is",
            fontsize=12, va="center", ha="center", color=RED)

    ax.text(4.6, 2.1, r"$0\;\;\;0\;\;\;0$", fontsize=26, va="center", ha="center", color=GREY)
    ax.text(8.1, 2.1, r"$1$", fontsize=26, va="center", ha="center", color=GREY)
    ax.text(6.3, 0.2, "the bottom row is always the same, which is what makes it 4 by 4",
            fontsize=10.5, va="center", ha="center", color=GREY, style="italic")

    # ---- what it is for, on the right ---------------------------------------------
    ax = fig.add_axes([0.45, 0.04, 0.54, 0.92])
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")

    # The description goes under its equation. Beside it, the longest equation runs into
    # its own label.
    # The third number is how far under its equation the description sits. A one line
    # equation needs little room. The one carrying a fraction is twice as tall and its
    # description has to clear the whole of it.
    rows = [
        (r"$p\,' = T\,p$",
         "a point is turned and shifted in one multiplication", 0.60),
        (r"$T_{a \rightarrow c} = T_{a \rightarrow b}\;\; T_{b \rightarrow c}$",
         "movements chain by multiplying", 0.60),
        (r"$T^{-1} = \left[\; R^{T}, \;\; -R^{T} t \;\right]$",
         "undoing a movement is an inverse", 0.62),
        (r"$T_{\mathrm{room},\,\mathrm{wrist}} = T_{\mathrm{room},\,\mathrm{device}}"
         r"\;\; T_{\mathrm{device},\,\mathrm{wrist}}$",
         "the hand, put into room coordinates", 0.62),
        (r"$T_{\mathrm{rel}}(k) = T(0)^{-1}\, T(k)$",
         "every pose measured from the window's first frame", 0.62),
        (r"$\theta = \arccos\!\left(\frac{\mathrm{tr}\,R - 1}{2}\right)$",
         "how far it turned, one number out of nine", 1.00),
    ]
    y = 9.3
    for maths, why, drop in rows:
        ax.text(0.1, y, maths, fontsize=19, va="center", ha="left")
        ax.text(0.35, y - drop, why, fontsize=11.5, va="center", ha="left", color="#555555")
        y -= 1.60

    fig.savefig(dest, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def load(label):
    """Time, the rotation, the translation and the stored angle, for every frame."""
    f = OUT / f"object_{label}_pose.csv"
    if not f.exists():
        return None
    t, R, p, deg, axis = [], [], [], [], []
    for row in csv.DictReader(f.open()):
        m = np.array([float(row[f"m{i}{j}"]) for i in range(3) for j in range(4)]).reshape(3, 4)
        t.append(float(row["time_s"]))
        R.append(m[:, :3])
        p.append(m[:, 3])
        deg.append(float(row["turned_deg"]))
        # The axis is blank on the first frame, where there is no rotation to have an axis.
        axis.append([float(row[f"axis_{a}"]) if row[f"axis_{a}"] else np.nan
                     for a in "xyz"])
    return np.array(t), np.stack(R), np.stack(p), np.array(deg), np.array(axis)


def matrix_text(T_rot, T_pos):
    """One 4 by 4 matrix as text, laid out so the four rows line up under each other."""
    lines = []
    for i in range(3):
        lines.append("  ".join(f"{v:7.3f}" for v in T_rot[i]) + f"  |{T_pos[i]:8.3f}")
    lines.append("  ".join(f"{v:7.3f}" for v in (0.0, 0.0, 0.0)) + f"  |{1.0:8.3f}")
    return "\n".join(lines)


def render(label, dest, row=False):
    got = load(label)
    if got is None:
        return None
    t, R, p, deg, axis = got
    t0 = t - t[0]
    # Centimetres, because the translation is the one part of this a person can picture and
    # metres put every interesting number three decimal places down.
    pc = p * 100

    # Two by two to read on a screen. One row when it has to sit under the text on a slide.
    if row:
        fig, axes = plt.subplots(1, 4, figsize=(22, 4.8))
    else:
        fig, grid = plt.subplots(2, 2, figsize=(13, 9))
        axes = grid.ravel()

    # --- how far it has turned ---------------------------------------------------------
    ax = axes[0]
    ax.plot(t0, deg, color="#6D2E46", lw=2)
    ax.set_title(f"how far it has turned since the first frame\nreached "
                 f"{deg.max():.0f} degrees", fontsize=11)
    ax.set_xlabel("seconds from the start of the window")
    ax.set_ylabel("degrees")
    ax.grid(alpha=0.25)

    # --- which way -----------------------------------------------------------------------
    ax = axes[1]
    for k, name in enumerate("xyz"):
        ax.plot(t0, axis[:, k], lw=1.6, label=f"axis {name}")
    ax.set_ylim(-1.1, 1.1)
    ax.set_title("which way it has turned, the axis as a unit vector\n"
                 "steady lines mean one consistent axis", fontsize=11)
    ax.set_xlabel("seconds from the start of the window")
    ax.set_ylabel("component")
    ax.legend(fontsize=9, ncol=3, loc="lower right")
    ax.grid(alpha=0.25)

    # --- where it has moved --------------------------------------------------------------
    ax = axes[2]
    for k, name in enumerate("xyz"):
        ax.plot(t0, pc[:, k], lw=1.8, label=f"t{name}")
    moved = float(np.linalg.norm(pc[-1] - pc[0]))
    ax.set_title(f"where it has moved, the translation t\nfinished {moved:.0f} cm "
                 f"from where it started", fontsize=11)
    ax.set_xlabel("seconds from the start of the window")
    ax.set_ylabel("centimetres")
    ax.legend(fontsize=9, ncol=3)
    ax.grid(alpha=0.25)

    # --- the matrix itself ----------------------------------------------------------------
    ax = axes[3]
    ax.axis("off")
    picks = [0, len(t) // 2, len(t) - 1]
    blocks = []
    for i in picks:
        blocks.append(f"t = {t0[i]:5.2f} s   turned {deg[i]:5.1f} deg\n"
                      + matrix_text(R[i], p[i]))
    ax.text(0.0, 1.0, "the matrix itself, at three moments\n\n" + "\n\n".join(blocks),
            family="monospace", fontsize=9.5, va="top", ha="left", transform=ax.transAxes)
    ax.set_title("T = [R t ; 0 1], relative to the first frame", fontsize=11)

    fig.suptitle(f"{label}:  the object's SE(3) pose, frame by frame", fontsize=13, y=0.99)
    fig.tight_layout()
    fig.savefig(dest, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return {"frames": len(t), "max_deg": float(deg.max()), "moved_cm": moved}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("only", nargs="*", help="labels to draw; default is all of them")
    ap.add_argument("--formula", action="store_true",
                    help="draw the algebra to outputs/se3_formula.png and stop")
    ap.add_argument("--row", action="store_true",
                    help="one row, which is the shape a slide has room for. The default is a grid")
    args = ap.parse_args()

    if args.formula:
        dest = OUT / "se3_formula.png"
        formula(dest)
        print(f"wrote {dest.relative_to(REPO)}")
        return 0

    mine = [r.get("label") or r["recording"]
            for r in csv.DictReader((REPO / "tools" / "object_runs.csv").open())]
    drawn = 0
    print(f"{'object':<16} {'frames':>7} {'turned':>8} {'moved':>8}")
    for label in mine:
        if args.only and label not in args.only:
            continue
        dest = OUT / (f"object_{label}_pose_row.png" if args.row
                      else f"object_{label}_pose.png")
        got = render(label, dest, row=args.row)
        if got is None:
            print(f"{label:<16} no pose file, run tools/object_pose.py first")
            continue
        drawn += 1
        print(f"{label:<16} {got['frames']:>7} {got['max_deg']:>7.0f}d {got['moved_cm']:>7.0f}cm")

    print(f"\ndrew {drawn} figures into outputs/")
    print("Run tools/object_pose.py --check to verify these matrices are genuine rotations.")
    return 0 if drawn else 1


if __name__ == "__main__":
    sys.exit(main())
