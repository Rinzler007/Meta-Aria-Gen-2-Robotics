#!/usr/bin/env python3
"""Merge the per frame surfaces into one model of the object.

Each frame holds the side of the object the cameras could see at that instant. Stacked
along the path the object travelled they make a smear, so the shape of the thing and the
route it took end up tangled in the same file. Looking at one frame gives you the shape
with hardly any points. Looking at the stack gives you plenty of points and the wrong
shape.

Separating them needs the object's pose in each frame, so every frame's points can be
carried back into the object's own frame where the object stands still. Pooled there they
would describe one object seen from many angles.

It works for a resting object and it fails for a carried one. The bowl in `scoop_01` never
moves, so its pose is one constant matrix and pooling narrows it from 52.5 cm to 24.7 cm,
which is the bowl. Every carried object comes out wider pooled than stacked.

The rotation is what breaks it. Taking only the path out barely changes the width, for eg.
`scoop_01` goes from 33.8 cm to 35.1 cm. Taking the turning out as well sends it to
77.9 cm. The rotation comes from the wrist, which is right about how far the object turned
while being too rough to line up surfaces. The grip check in `tools/object_pose.py` shows
the object sliding 1.5 to 5 cm inside the hand across a window. At the 15 cm or so
between wrist and object that is roughly 20 degrees of error.

So this builds a model, measures it against the stack and keeps it only where it is
genuinely narrower. A model that comes out wider is not written.

    python3 tools/object_model.py
    python3 tools/object_model.py pour_01
"""

import argparse
import csv
import re
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "outputs"


def load_pose(name):
    """The 3 by 3 rotation and the position for every frame, straight from the pose file."""
    f = OUT / f"object_{name}_pose.csv"
    if not f.exists():
        return None
    t, R, p = [], [], []
    for row in csv.DictReader(f.open()):
        m = np.array([float(row[f"m{i}{j}"]) for i in range(3) for j in range(4)]).reshape(3, 4)
        t.append(float(row["time_s"]))
        R.append(m[:, :3])
        p.append(m[:, 3])
    return np.array(t), np.stack(R), np.stack(p)


def build(name):
    """Pool every frame's points into the object's own frame."""
    npz = OUT / f"object_{name}_clouds.npz"
    traj = OUT / f"object_{name}_trajectory.csv"
    got = load_pose(name)
    if not npz.exists() or not traj.exists() or got is None:
        return None
    pt, pR, pp = got

    rows = list(csv.DictReader(traj.open()))
    ct = np.array([float(r["time_s"]) for r in rows])
    z = np.load(npz)
    keys = sorted(k for k in z.files if k.startswith("frame_"))
    if len(keys) != len(ct):
        # The trajectory only carries frames where points were found, so the clouds and the
        # rows line up one to one by construction. A mismatch means something else is wrong.
        return None

    pooled = []
    for k, tc in zip(keys, ct):
        pts = z[k]
        if len(pts) < 5:
            continue
        j = int(np.argmin(np.abs(pt - tc)))
        if abs(pt[j] - tc) > 0.05:
            continue
        # Undo the frame's pose. What is left is the object sitting still in its own frame,
        # whichever way it happened to be turned when this frame was taken.
        pooled.append((pts - pp[j]) @ pR[j])
    if not pooled:
        return None
    return np.vstack(pooled), pt, pR, pp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*")
    a = ap.parse_args()

    runs = sorted(OUT.glob("object_*_clouds.npz"))
    done = 0
    print(f"{'object':<14} {'frames':>7} {'points':>10} {'stack':>8} {'model':>8}  shrink")
    for npz in runs:
        name = re.sub(r"^object_|_clouds\.npz$", "", npz.name)
        if a.only and name not in a.only:
            continue
        built = build(name)
        if built is None:
            continue
        pooled, pt, pR, pp = built

        z = np.load(npz)
        keys = [k for k in z.files if k.startswith("frame_")]
        stack = np.vstack([z[k] for k in keys])
        # How wide the smear is against how wide the object is. A big drop means the stack
        # was mostly travel.
        d_stack = float(np.linalg.norm(stack.max(0) - stack.min(0)) * 100)
        lo, hi = np.percentile(pooled, [1, 99], axis=0)
        d_model = float(np.linalg.norm(hi - lo) * 100)

        # A model wider than the stack it came from has been scattered by the pose, not
        # assembled by it, so it is measured and discarded rather than written out.
        better = d_model < d_stack
        if better:
            np.savez_compressed(OUT / f"object_{name}_model.npz",
                                model=pooled.astype(np.float32),
                                pose_time_s=pt, pose_rotation=pR, pose_position=pp)
            done += 1
        print(f"{name:<14} {len(keys):>7} {len(pooled):>10,} {d_stack:7.1f}cm {d_model:7.1f}cm  "
              f"{(1 - d_model / d_stack) * 100:4.0f}%  {'written' if better else 'discarded'}")

    print(f"\nwrote {done} of {len(runs)} models into outputs/")
    print("Stack is how wide the per frame clouds are laid along the path. Model is how wide")
    print("they are once the pose is taken out, across the middle 98 per cent. A model wider")
    print("than its stack means the pose scattered the points, so it is discarded.")


if __name__ == "__main__":
    main()
