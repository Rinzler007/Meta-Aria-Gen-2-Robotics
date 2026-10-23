#!/usr/bin/env python3
"""Build a model of a carried object by correcting the rotation the wrist gives.

Where this starts. `tools/object_model.py` pools every frame's points into the object's own
frame using the pose from the wrist and that already works. What it leaves behind is the
rotation error. The object slides 1.5 to 5 cm inside the grip across a window, which at the
15 cm between wrist and object is around 20 degrees. Twenty degrees is right about how far
a jug turned. It is far too rough to lay two views of a jug on top of each other and the
jugs are where it shows: they pool to 45 to 52 cm where a spoon pools to 12 to 20.

Why not line consecutive frames up instead. That was tried and it is in the docstring of
`tools/object_pose.py`. Fitting each frame to the one before it and multiplying the results
together drifts 94 to 105 degrees around a window and back, because a spoon or a jug is
smooth enough that a fit can slide along its own surface at no cost. Each fit looks fine on
its own and a hundred of them in a row are a random walk.

What this does differently. Every frame is fitted to the same growing model. Its neighbour
never comes into it. The wrist pose puts the frame roughly in place, a fit corrects it against
everything gathered so far and the corrected points join the model. Nothing is multiplied
together, so an error in one frame stays in that frame. Nothing carries it into
the frames after it. That is the whole idea: the drift came from chaining and this does not
chain.

    python3 tools/object_model_refine.py
    python3 tools/object_model_refine.py pour_01 pick_02

It prints the width of the stack, the width from the wrist pose alone and the width after
the correction, so the three can be read against each other. A model is written to
`outputs/object_<label>_model_refined.npz` only when it is narrower than both.

How to read the widths. The stack is how wide the per frame clouds are when laid along the
path the object travelled, so it holds the object and the journey together. The model is
how wide they are once the pose is taken out, across the middle 98 per cent so that one
stray point cannot set the number. A model narrower than its stack has separated the shape
from the path. A model wider has been scattered.

What it found. The correction earns its place on the objects that turn and changes nothing
on the ones that do not. Two of the three jugs come in by about 9 cm, `pour_02` from 46.5
to 37.6 and `pour_03` from 52.1 to 43.7. The spoons and the tins move by a centimetre
either way, which says the wrist rotation was already good enough for them. Eight of the
thirteen windows end up narrower than both the stack and the wrist's own answer and are
written out. The rest are measured and discarded.

The residuals are the warning attached to all of this. A frame sits a median of 0.7 to
3.0 mm from the model it was fitted to, which is far tighter than the model is wide. A fit
can settle snugly in the wrong place on a smooth surface, so a small residual is not
evidence the frame landed correctly. Read the width, which is the thing that would be
wrong if it had not.
"""

import argparse
import csv
import re
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
OUT = REPO / "outputs"

import object_model as om

# How many rounds of fitting each frame gets. The wrist already puts the frame within about
# twenty degrees, so this is a correction and not a search and a handful of rounds is
# enough for one. More rounds mostly give a smooth surface more chances to slide.
ICP_ROUNDS = 15

# A pair further apart than this is not the same bit of surface seen twice. It is one
# frame's point and some unrelated part of the model and letting it vote drags the fit
# towards whatever else is nearby. Three centimetres is wide enough to close a twenty
# degree error on an object the size of a jug and tight enough to reject the far side.
PAIR_CM = 3.0

# How many points the model is allowed to carry. Every frame adds a few hundred and the
# nearest neighbour search is what costs time, so the model is thinned as it grows. The
# thinning is random, which keeps the surface evenly covered. Keeping the newest points
# would quietly turn the model back into the last few frames.
MAX_MODEL = 20000

# A frame with fewer points than this says nothing about rotation. Fitting it would be
# fitting noise, so its points are placed by the wrist alone and it does not vote.
MIN_POINTS = 30


def kabsch(a, b):
    """The rotation and translation that best carries points `a` onto points `b`.

    This is the closed form least squares answer and it is worth saying why the last step is
    there. The singular value decomposition gives the best orthogonal matrix and an
    orthogonal matrix can be a reflection as well as a rotation. A reflection would fit a
    mirrored copy of the object onto itself and score beautifully while being physically
    impossible, so when the determinant comes out negative we flip the smallest singular
    direction, which is the cheapest correction that lands back on a true rotation.
    """
    ca, cb = a.mean(axis=0), b.mean(axis=0)
    U, _S, Vt = np.linalg.svd((a - ca).T @ (b - cb))
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
    return R, cb - R @ ca


def fit_to_model(pts, tree, model):
    """Correct one frame's placement against the model gathered so far.

    Returns the rotation and translation to apply and the median distance left over, which
    is how we tell a fit that found the surface from one that gave up.
    """
    R_total = np.eye(3)
    t_total = np.zeros(3)
    current = pts
    residual = np.inf
    for _ in range(ICP_ROUNDS):
        dist, idx = tree.query(current)
        keep = dist < PAIR_CM / 100.0
        # Too few surviving pairs and there is nothing to fit. We stop and hand back
        # whatever correction we had reached, which may be none at all.
        if keep.sum() < MIN_POINTS:
            break
        R, t = kabsch(current[keep], model[idx[keep]])
        current = current @ R.T + t
        # The corrections compose, so the caller gets one rotation and one translation.
        # A list of fifteen small ones would be the same answer in a harder shape.
        R_total = R @ R_total
        t_total = R @ t_total + t
        residual = float(np.median(dist[keep]))
    return R_total, t_total, residual


def refine(name):
    """Pool the frames into the object frame, correcting each one against the growing model."""
    built = om.build(name)
    if built is None:
        return None
    wrist_pooled, pt, pR, pp = built

    z = np.load(OUT / f"object_{name}_clouds.npz")
    rows = list(csv.DictReader((OUT / f"object_{name}_trajectory.csv").open()))
    ct = np.array([float(r["time_s"]) for r in rows])
    # Where the object stands in the room each frame. The pose file's translation is the
    # displacement since the window opened and cannot be used for this, which is the same
    # point `tools/object_model.py` makes where it pools its frames.
    centre = np.array([[float(r["world_x"]), float(r["world_y"]), float(r["world_z"])]
                       for r in rows])
    keys = sorted(k for k in z.files if k.startswith("frame_"))

    model = None
    residuals = []
    corrected = 0
    for i, (k, tc) in enumerate(zip(keys, ct)):
        pts = z[k]
        if len(pts) < 5:
            continue
        j = int(np.argmin(np.abs(pt - tc)))
        if abs(pt[j] - tc) > 0.05:
            continue
        # The wrist's answer, which is where this frame would sit without any correction.
        guess = (pts - centre[i]) @ pR[j]
        if model is None:
            # The first frame defines the object's frame. There is nothing to fit it to and
            # nothing it could be wrong about, since every later frame is placed relative
            # to it.
            model = guess
            continue
        if len(guess) < MIN_POINTS:
            model = np.vstack([model, guess])
        else:
            R, t, res = fit_to_model(guess, cKDTree(model), model)
            residuals.append(res)
            corrected += 1
            model = np.vstack([model, guess @ R.T + t])
        if len(model) > MAX_MODEL:
            # Thinned at random, so the model keeps describing every view it has seen.
            # Keeping the newest points would let it drift towards whichever frames came last.
            model = model[np.random.default_rng(0).choice(len(model), MAX_MODEL, replace=False)]
    if model is None:
        return None
    return wrist_pooled, model, residuals, corrected


def width_cm(pts):
    """How wide a cloud is across the middle 98 per cent, as a diagonal in centimetres.

    Why the middle 98 and not all of it ? Because a single reconstructed point a metre off
    the object would set the number on its own and the question here is how big the object
    came out and not how far the worst stray point landed.
    """
    lo, hi = np.percentile(pts, [1, 99], axis=0)
    return float(np.linalg.norm(hi - lo) * 100)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("only", nargs="*", help="labels to run; default is all of them")
    args = ap.parse_args()

    found = sorted(OUT.glob("object_*_clouds.npz"))
    written = 0
    scored = 0
    print(f"{'object':<16} {'stack':>8} {'wrist':>8} {'fitted':>8} {'residual':>9}  result")
    for npz in found:
        name = re.sub(r"^object_|_clouds\.npz$", "", npz.name)
        if args.only and name not in args.only:
            continue
        got = refine(name)
        if got is None:
            continue
        wrist_pooled, model, residuals, corrected = got
        scored += 1

        z = np.load(npz)
        stack = np.vstack([z[k] for k in z.files if k.startswith("frame_")])
        d_stack = width_cm(stack)
        d_wrist = width_cm(wrist_pooled)
        d_model = width_cm(model)
        res_mm = float(np.median(residuals)) * 1000 if residuals else float("nan")

        # Narrower than the stack means the pose separated the shape from the path.
        # Narrower than the wrist's own answer means the correction earned its place. Both
        # have to hold or the file is not written.
        better = d_model < d_stack and d_model < d_wrist
        if better:
            np.savez_compressed(OUT / f"object_{name}_model_refined.npz",
                                model=model.astype(np.float32))
            written += 1
        print(f"{name:<16} {d_stack:7.1f}cm {d_wrist:7.1f}cm {d_model:7.1f}cm "
              f"{res_mm:8.1f}mm  {'written' if better else 'discarded'}"
              f"  ({corrected} frames fitted)")

    print(f"\nwrote {written} of {scored} models into outputs/")
    print("Stack holds the object and its journey together. Wrist is the pooled cloud using")
    print("the wrist rotation alone. Fitted is the same after each frame is corrected against")
    print("the growing model. Residual is the median distance left between a frame and the")
    print("model it was fitted to, so a small residual with a wide model means the fit found")
    print("somewhere to sit that was not the right place.")


if __name__ == "__main__":
    main()
