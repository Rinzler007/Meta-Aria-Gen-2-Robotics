#!/usr/bin/env python3
"""Draw the two deliverables for one recording, so that each can be read on its own.

The problem this fixes. The old figure drew every frame's points at the position the object
occupied in that frame, all in one picture. A hundred and twenty copies of a soup tin laid
along the path it travelled makes a smear. You cannot see the tin, you cannot see the path
and nobody looking at it could say what they were being shown. The shape and the journey
were tangled together in the same picture.

They are two separate deliverables and this draws them separately.

    python3 tools/render_object_cloud.py                 # every object run
    python3 tools/render_object_cloud.py pick_02 pour_01 # just these

The four panels.

**One frame** is the surface the two cameras could see at a single instant. It is thin,
because there is no depth sensor on these glasses and depth comes from matching what the
two forward cameras each saw. Neither can see round the back. This panel exists so nobody
mistakes the next one for something a single frame gave us.

**The object** is every frame carried back into the object's own frame, where the object
stands still and the path falls away. Each frame contributes the face it could see, so
pooled they cover the object from every angle the demonstration happened to show. This is
the point cloud deliverable.

It is drawn as a density and not as dots. A hundred thousand dots at any useful size paint
a solid block. A solid block tells you nothing about where the object actually is.
Shading by how many points fall in each small cell separates the two things in the cloud.
The dark core is the object. The pale halo around it is stereo noise, which throws a few
points a long way out of every one of these clouds. That is where the haze comes from and
the density view is what makes it possible to see past it.

**The path from above** is the object's centre through the room, which is the trajectory
deliverable. No surface points at all, so the line is the only thing to read.

**The height against time** is the same path seen from the side, which is where a lift or a
pour shows up and where a flat carry across a table does not.

It needs `tools/object_pose.py` and `tools/object_model.py` to have run, since the object's
own frame is what the pose defines and the model is what the pooling produces.
"""

import argparse
import csv
import re
import sys
from pathlib import Path

import numpy as np
import matplotlib
# A file backend, chosen before pyplot loads, because this runs in a terminal with no
# window for a figure to appear in.
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "outputs"
sys.path.insert(0, str(REPO / "tools"))

import object_model as om

# Which axis of the room frame points upwards ? We checked. Nobody assumed. The spoon is
# lifted out of a bowl during these hundred frames and z is the axis that rises steadily
# with it, gaining 9.1 cm between the first frames and the last while the other two wander
# without going anywhere in particular.
UP = 2

# The two axes that are not up, kept in this order so every panel agrees with every other.
FLAT = [i for i in range(3) if i != UP]
AXIS = "xyz"


def frame_to_show(clouds, keys):
    """Which single frame to draw as the example of what one frame gives you.

    The fullest one. A frame where stereo found almost nothing would be honest about the
    worst case and useless as an illustration of what the method does. This panel is here
    to show the shape of the problem. Finding its floor is a different question.
    """
    sizes = [len(clouds[k]) for k in keys]
    return keys[int(np.argmax(sizes))], max(sizes)


def render(label, dest):
    """Draw the four panels for one object run. Returns what was measured, for printing."""
    npz = OUT / f"object_{label}_clouds.npz"
    traj_csv = OUT / f"object_{label}_trajectory.csv"
    if not npz.exists() or not traj_csv.exists():
        return None

    built = om.build(label)
    if built is None:
        return None
    model = built[0]

    z = np.load(npz)
    keys = sorted(k for k in z.files if k.startswith("frame_"))
    best_key, best_n = frame_to_show(z, keys)

    rows = list(csv.DictReader(traj_csv.open()))
    t_s = np.array([float(r["time_s"]) for r in rows])
    path = np.array([[float(r["world_x"]), float(r["world_y"]), float(r["world_z"])]
                     for r in rows])

    # Everything is drawn in centimetres about its own middle. The room frame's origin sits
    # wherever the recording happened to start, so raw coordinates run to metres and tell a
    # reader nothing. Taking the middle out leaves the shape and the distance travelled,
    # which are the two things worth reading off a picture.
    one = (z[best_key] - z[best_key].mean(axis=0)) * 100
    obj = (model - np.median(model, axis=0)) * 100
    way = (path - path[0]) * 100

    # Two by two. Four panels in a row leaves each one too small to read on a slide, which
    # is where these end up.
    fig, grid = plt.subplots(2, 2, figsize=(13, 10.5))
    axes = grid.ravel()

    # --- one frame -------------------------------------------------------------------
    ax = axes[0]
    ax.scatter(one[:, FLAT[0]], one[:, UP], s=3, color="#36454F", alpha=0.55)
    ax.set_aspect("equal")
    ax.set_title(f"one frame\n{best_n:,} points, the side the cameras saw", fontsize=11)
    ax.set_xlabel(f"{AXIS[FLAT[0]]} (cm)")
    ax.set_ylabel(f"{AXIS[UP]}, height (cm)")
    ax.grid(alpha=0.25)

    # --- the object ------------------------------------------------------------------
    ax = axes[1]
    # The middle 98 per cent sets the limits. A handful of points a long way out would
    # otherwise shrink the object to a dot in the corner of its own panel, which is what
    # depth noise does to every one of these clouds.
    lo, hi = np.percentile(obj, [1, 99], axis=0)
    pad = 0.12 * max(hi - lo)
    xlim = (lo[FLAT[0]] - pad, hi[FLAT[0]] + pad)
    ylim = (lo[UP] - pad, hi[UP] + pad)
    # A logarithmic count scale, because the core holds hundreds of times more points than
    # the halo. On a linear scale the halo disappears entirely and the picture stops being
    # honest about how much noise is in the cloud.
    hb = ax.hexbin(obj[:, FLAT[0]], obj[:, UP], gridsize=70, cmap="magma_r",
                   bins="log", extent=(*xlim, *ylim), mincnt=1)
    ax.set_aspect("equal")
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    width = float(np.linalg.norm(hi - lo))
    ax.set_title(f"the object, every frame pooled\n{len(model):,} points, "
                 f"{width:.0f} cm across the middle 98 per cent", fontsize=11)
    ax.set_xlabel(f"{AXIS[FLAT[0]]} (cm)")
    ax.set_ylabel(f"{AXIS[UP]}, height (cm)")
    cbd = fig.colorbar(hb, ax=ax, fraction=0.045, pad=0.02)
    cbd.set_label("points per cell")
    ax.grid(alpha=0.2)

    # --- the path from above ----------------------------------------------------------
    ax = axes[2]
    sc = ax.scatter(way[:, FLAT[0]], way[:, FLAT[1]], c=t_s - t_s[0], cmap="viridis", s=14)
    ax.plot(way[:, FLAT[0]], way[:, FLAT[1]], color="#999999", lw=1, zorder=0)
    # Start and finish marked, because a coloured line alone leaves a reader guessing which
    # end it began at.
    ax.plot(way[0, FLAT[0]], way[0, FLAT[1]], "o", ms=11, mfc="none", mec="black", mew=2)
    ax.plot(way[-1, FLAT[0]], way[-1, FLAT[1]], "X", ms=12, color="black")
    ax.set_aspect("equal")
    travelled = float(np.linalg.norm(way[-1] - way[0]))
    ax.set_title(f"the path from above\nfinished {travelled:.0f} cm from where it started",
                 fontsize=11)
    ax.set_xlabel(f"{AXIS[FLAT[0]]} (cm)")
    ax.set_ylabel(f"{AXIS[FLAT[1]]} (cm)")
    ax.grid(alpha=0.25)

    # --- the height against time -------------------------------------------------------
    ax = axes[3]
    ax.plot(t_s - t_s[0], way[:, UP], color="#B85042", lw=2)
    rise = float(way[:, UP].max() - way[:, UP].min())
    ax.set_title(f"the height against time\nrose and fell {rise:.0f} cm", fontsize=11)
    ax.set_xlabel("seconds from the start of the window")
    ax.set_ylabel(f"{AXIS[UP]}, height (cm)")
    ax.grid(alpha=0.25)

    cb = fig.colorbar(sc, ax=axes[2], fraction=0.045, pad=0.02)
    cb.set_label("seconds")

    fig.suptitle(f"{label}:  top row is the object, bottom row is where it went",
                 fontsize=13, y=0.99)
    fig.tight_layout()
    # Saved before anything can close the figure. Calling show() first closes it and a
    # savefig afterwards writes a blank white image, which has caught this project out.
    fig.savefig(dest, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    return {"frames": len(keys), "best_frame_points": best_n, "model_points": len(model),
            "object_cm": width, "travelled_cm": travelled, "rise_cm": rise}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("only", nargs="*", help="labels to draw; default is all of them")
    args = ap.parse_args()

    found = sorted(OUT.glob("object_*_clouds.npz"))
    mine = {r.get("label") or r["recording"]
            for r in csv.DictReader((REPO / "tools" / "object_runs.csv").open())}

    drawn = 0
    print(f"{'object':<16} {'frames':>7} {'best frame':>11} {'model':>9} "
          f"{'object':>8} {'travelled':>10} {'rise':>7}")
    for npz in found:
        label = re.sub(r"^object_|_clouds\.npz$", "", npz.name)
        if args.only and label not in args.only:
            continue
        # Runs of the pipeline on somebody else's recording live in this folder too, put
        # there so the grip detection could be scored outside our lab. They are not our
        # demonstrations, so they stay out of our figures unless they are asked for by name.
        if not args.only and label not in mine:
            continue
        dest = OUT / f"object_{label}_cloud.png"
        got = render(label, dest)
        if got is None:
            print(f"{label:<16} needs tools/object_pose.py to have run, skipped")
            continue
        drawn += 1
        print(f"{label:<16} {got['frames']:>7} {got['best_frame_points']:>10,} "
              f"{got['model_points']:>8,} {got['object_cm']:>7.0f}cm "
              f"{got['travelled_cm']:>9.0f}cm {got['rise_cm']:>6.0f}cm")

    print(f"\ndrew {drawn} figures into outputs/")
    print("One frame is what the cameras saw at an instant. The object is every frame pooled")
    print("into the object's own frame. The path and the height are the trajectory, drawn on")
    print("their own so the shape of the object cannot be mistaken for the shape of the path.")
    return 0 if drawn else 1


if __name__ == "__main__":
    sys.exit(main())
