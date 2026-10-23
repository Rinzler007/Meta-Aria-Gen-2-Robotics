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

It works on all thirteen windows. A spoon comes out 12 to 20 cm across, a soup tin 14 to
16, the red bowl 24 and a jug 45 to 52. The stacks they came from run 25 to 93 cm, so for
the carried objects most of what the stack held was the journey and taking the pose out
leaves the thing itself.

The jugs are the weak case and the reason is the rotation. A jug is the object that turns
most while it is carried, so it is the one most exposed to the rotation being rough. The
rotation comes from the wrist, which is right about how far the object turned while being
too rough to lay two views of a surface on top of each other. The grip check in
`tools/object_pose.py` shows the object sliding 1.5 to 5 cm inside the hand across a
window and at the 15 cm or so between wrist and object that is roughly 20 degrees.
`tools/object_model_refine.py` corrects that frame by frame and brings two of the three
jugs in by 9 cm.

This builds the model, measures it against the stack and keeps it only where it is
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
    """The 3 by 3 rotation and the displacement for every frame, from the pose file.

    The matrix in that file is the pose relative to the first frame, which is what the
    professor asked for and what `tools/object_pose.py` writes. Its translation is therefore
    how far the object has moved since the window opened, starting at zero. It is not where
    the object is in the room and using it as though it were is what the comment in `build`
    is about.
    """
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
    # Where the object actually is in the room, frame by frame. This is the centre the
    # points have to be taken about before the rotation is undone and it has to come from
    # here because the pose file carries displacement since the first frame instead.
    centre = np.array([[float(r["world_x"]), float(r["world_y"]), float(r["world_z"])]
                       for r in rows])
    z = np.load(npz)
    keys = sorted(k for k in z.files if k.startswith("frame_"))
    if len(keys) != len(ct):
        # The trajectory only carries frames where points were found, so the clouds and the
        # rows line up one to one by construction. A mismatch means something else is wrong.
        return None

    pooled = []
    for i, (k, tc) in enumerate(zip(keys, ct)):
        pts = z[k]
        if len(pts) < 5:
            continue
        j = int(np.argmin(np.abs(pt - tc)))
        if abs(pt[j] - tc) > 0.05:
            continue
        # Undo the frame's pose. Take the points about where the object was standing, then
        # turn them back by however far it had turned and what is left is the object
        # sitting still in its own frame whichever way it happened to be facing.
        #
        # The centre has to be the object's position in the room and not the translation in
        # the pose file. Subtracting a displacement of a few centimetres from points that
        # sit two thirds of a metre from the room origin leaves them out there and the
        # rotation then swings them around the origin on a two thirds of a metre arm. That
        # turns a jug into a cloud a metre wide and it is why every carried object used to
        # come out wider pooled than stacked.
        pooled.append((pts - centre[i]) @ pR[j])
    if not pooled:
        return None
    return np.vstack(pooled), pt, pR, pp


def width_cm(pts):
    """How wide a cloud is across the middle 98 per cent, as a diagonal in centimetres.

    Why the middle 98 and not all of it ? Because one reconstructed point a metre off the
    object would set the number on its own and what we want to know is how big the object
    came out and not how far the worst stray point landed.
    """
    lo, hi = np.percentile(pts, [1, 99], axis=0)
    return float(np.linalg.norm(hi - lo) * 100)


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
        # was mostly travel. Both are measured across the middle 98 per cent of their
        # points and they have to be measured the same way or the comparison is rigged:
        # the full extent of the stack against the trimmed extent of the model would show a
        # drop even where the pose did nothing at all.
        d_stack = width_cm(stack)
        d_model = width_cm(pooled)

        # A model wider than the stack it came from has been scattered by the pose, not
        # assembled by it, so it is measured and discarded. Nothing is written out.
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
