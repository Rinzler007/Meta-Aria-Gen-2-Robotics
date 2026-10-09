#!/usr/bin/env python3
"""Redraw the accumulated object point cloud figure from its npz.

The equivalent figure used to exist in the repository without any code that produced it, so a
fresh clone could look at it but never regenerate it. That is the one thing a deliverable
should never be, so it lives here now.

It reads `outputs/object_<recording>_clouds.npz`, which is committed, rather than the
recording, which is far too large for git and is excluded. So this is the one thing in the
repository that runs on a fresh clone with no data download and no model weights.

    python3 tools/render_object_cloud.py                  # the most recent object run
    python3 tools/render_object_cloud.py --clouds <path>  # a specific one

The clouds themselves come from `notebooks/object_pipeline.ipynb`, which is the expensive part.
That notebook draws this figure too. This script exists so the drawing can be redone without
recomputing anything.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import matplotlib
# A file backend, chosen before pyplot loads, because this runs in a terminal with no
# window for a figure to appear in.
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Which axis of the room frame points upwards ? We checked rather than assumed. The spoon is
# lifted out of a bowl during these hundred frames, and z is the axis that rises steadily
# with it, gaining 9.1 cm between the first frames and the last while the other two wander
# without going anywhere in particular.
#
# Note we use that rise rather than the raw span to decide. Depth noise throws a handful of
# points a long way out, so z reads 44.8 cm across its full extent while 99 percent of the
# cloud sits inside 23.3 cm. Two points out of 20,518 account for the difference. A span is
# the wrong statistic to reason from here, and reading one off a plot is how you talk
# yourself into believing an axis is mislabelled when it is not.
UP = 2


def load(npz_path):
    """The per frame clouds and the trajectory, straight out of the npz."""
    z = np.load(npz_path)

    # Each frame contributes the part of the object surface the two cameras could see from
    # where they were at that moment, so the frames have different point counts.
    keys = sorted(k for k in z.files if k.startswith("frame_"))
    clouds = [z[k] for k in keys]

    # Every point gets labelled with the frame it came from, which is what lets the colour
    # carry time rather than just making the picture look busy.
    frame_of = np.concatenate([np.full(len(c), i) for i, c in enumerate(clouds)])
    pts = np.vstack(clouds)

    # Columns are frame, x, y, z. The object centre per frame, which is the trajectory.
    traj = z["trajectory_world"][:, 1:4]

    return pts, frame_of, traj, len(clouds)


def render(pts, frame_of, traj, out_path):
    """Three views of the same cloud, because no single one shows the whole shape."""
    # The room frame has its origin wherever the recording happened to start, so the raw
    # coordinates run to several metres and mean nothing to a reader. Taking the centre out
    # and working in centimetres leaves only the shape, which is the part worth looking at.
    centre = pts.mean(axis=0)
    p = (pts - centre) * 100
    t = (traj - centre) * 100

    # Two axes we are not calling "up", kept in order so the horizontal panels stay
    # consistent with each other.
    flat = [i for i in range(3) if i != UP]
    ax_name = "xyz"

    fig = plt.figure(figsize=(17, 5.5))

    # --- perspective, which is the only view that shows the shape as a solid thing ------
    ax = fig.add_subplot(1, 3, 1, projection="3d")
    ax.scatter(p[:, 0], p[:, 1], p[:, 2], c=frame_of, cmap="viridis", s=1, alpha=0.6)
    ax.plot(t[:, 0], t[:, 1], t[:, 2], color="crimson", lw=2)
    ax.set_xlabel("x (cm)")
    ax.set_ylabel("y (cm)")
    ax.set_zlabel("z (cm)")
    ax.set_title("in perspective", fontsize=11)

    # --- from the side, which is where the lift is visible -----------------------------
    ax = fig.add_subplot(1, 3, 2)
    ax.scatter(p[:, flat[0]], p[:, UP], c=frame_of, cmap="viridis", s=1, alpha=0.6)
    ax.plot(t[:, flat[0]], t[:, UP], color="crimson", lw=2,
            label="object centre, frame by frame")
    # Equal aspect, or the lift gets stretched to fill the box and stops being comparable
    # with the panel beside it.
    ax.set_aspect("equal")
    ax.set_xlabel(f"{ax_name[flat[0]]} (cm)")
    ax.set_ylabel(f"{ax_name[UP]}, height (cm)")
    ax.set_title("from the side, the lift", fontsize=11)
    ax.legend(fontsize=9, loc="lower left")
    ax.grid(alpha=0.25)

    # --- from above, which shows how far it was carried across the table ---------------
    ax = fig.add_subplot(1, 3, 3)
    sc = ax.scatter(p[:, flat[0]], p[:, flat[1]], c=frame_of, cmap="viridis", s=1, alpha=0.6)
    ax.plot(t[:, flat[0]], t[:, flat[1]], color="crimson", lw=2)
    ax.set_aspect("equal")
    ax.set_xlabel(f"{ax_name[flat[0]]} (cm)")
    ax.set_ylabel(f"{ax_name[flat[1]]} (cm)")
    ax.set_title("from above", fontsize=11)
    ax.grid(alpha=0.25)

    # One colourbar for all three panels, since they share the one scale. Frame number runs
    # from the start of the tracked window to the end, so the colour is time.
    cb = fig.colorbar(sc, ax=fig.axes, fraction=0.015, pad=0.02)
    cb.set_label("frame number")

    # Save before anything can close the figure. Calling show() first closes it and the
    # savefig afterwards writes a blank white image, which has caught this project out.
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clouds", default=None, help="path to an object_*_clouds.npz")
    ap.add_argument("--out", default=None, help="where to write the png")
    args = ap.parse_args()

    # The repository is one level up from tools/, so this works from any directory.
    repo = Path(__file__).resolve().parent.parent
    outputs = repo / "outputs"

    if args.clouds:
        clouds = Path(args.clouds)
    else:
        # Default to whichever object run is present. There is normally one per recording,
        # named by the pipeline notebook, so we take the most recently written rather than
        # hardcoding a name that goes stale the moment a new recording is processed.
        found = sorted(outputs.glob("object_*_clouds.npz"), key=lambda f: f.stat().st_mtime)
        if not found:
            print(f"no object_*_clouds.npz in {outputs}", file=sys.stderr)
            print("run notebooks/object_pipeline.ipynb first, which is what writes it.",
                  file=sys.stderr)
            return 1
        clouds = found[-1]

    # The figure sits beside its data and carries the same stem, so it is always obvious
    # which run produced which picture.
    out = Path(args.out) if args.out else clouds.with_name(
        clouds.name.replace("_clouds.npz", "_cloud.png"))

    # An explicitly named file that does not exist deserves a plain message rather than a
    # stack trace out of numpy.
    if not clouds.is_file():
        print(f"no cloud data at {clouds}", file=sys.stderr)
        return 1

    pts, frame_of, traj, n_frames = load(clouds)

    print(f"read {clouds.name}")
    print(f"  {len(pts):,} points across {n_frames} frames")
    for i, name in enumerate("xyz"):
        updown = "  <- up" if i == UP else ""
        col = pts[:, i] * 100
        # The full extent and the middle 98 percent, because depth noise puts a few points
        # a long way from the object and the two numbers tell very different stories.
        robust = np.percentile(col, 99) - np.percentile(col, 1)
        print(f"  {name} span: {np.ptp(col):5.1f} cm full, "
              f"{robust:5.1f} cm across the middle 98 percent{updown}")

    render(pts, frame_of, traj, out)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
