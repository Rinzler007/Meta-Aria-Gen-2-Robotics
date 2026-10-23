#!/usr/bin/env python3
"""Check the object based contact detection against somebody else's labels.

Why a second external check. The first grip detection read the shape of the hand and scored
46.9 per cent on Meta's `cook_0`, which is guessing. `tools/grip_features.py` shows that no
hand shape does better there, so the signal had to come from somewhere else, and
`tools/grip_from_object.py` takes it from the distance between the hand and the object the
pipeline is tracking. That change has to be scored outside our own lab too or it is the
same mistake again.

How their labels can judge one object. Their `hand_object_interaction` file marks the object
a hand is touching, frame by frame and it carries a mask for that object. It does not say
which object and it carries nothing at all on a frame where nobody is touching anything. So
"are they marking contact right now" is the wrong question: they could be marking a different
object entirely. The right question is whether the object they mark is the object we are
tracking, which their mask answers. A frame counts as contact for our object when a
contact mask on that frame overlaps our object's mask.

    python3 tools/check_contact_against_pilot.py cook0_avocado reference/pilot_cook_0

It needs the pipeline to have been run on their recording first, which
`tools/pilot_runs.csv` sets up:

    python3 tools/run_all_objects.py --runs tools/pilot_runs.csv \\
        --notebook notebooks/_pilot_scratch.ipynb

The window is half an avocado held in the left hand, put down on the board partway through.
Their labels stop marking it at 64.5 s and our detection has a release to find that nobody
on this project chose.
"""

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

import numpy as np
from pycocotools import mask as cocomask
from scipy.spatial import cKDTree

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import grip_from_object as gfo

CONTACT_CATEGORY = 3
# How much of our object a contact mask has to cover before we accept they are talking
# about the same thing. A tenth is low on purpose. Their mask covers the whole object while
# ours covers the part stereo reconstructed and the camera could see, so a large overlap is
# not available even when both are right about the same avocado.
MIN_OVERLAP = 0.10


def decode(entry):
    """Their masks are run length encoded, which `pycocotools` turns back into pixels."""
    seg = dict(entry["segmentation"])
    if isinstance(seg["counts"], str):
        seg["counts"] = seg["counts"].encode()
    return cocomask.decode(seg)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("label", help="the label the pipeline ran under, for eg. cook0_avocado")
    ap.add_argument("folder", help="their sequence folder")
    args = ap.parse_args()

    folder = Path(args.folder)
    runs = {r.get("label") or r["recording"]: r
            for r in csv.DictReader((REPO / "tools" / "pilot_runs.csv").open())}
    if args.label not in runs:
        sys.exit(f"{args.label} is not in tools/pilot_runs.csv")
    row = runs[args.label]
    start_s, duration_s = float(row["start_s"]), float(row["duration_s"])

    traj_path = REPO / "outputs" / f"object_{args.label}_trajectory.csv"
    if not traj_path.exists():
        sys.exit(f"no {traj_path.relative_to(REPO)}; run the pipeline on their recording first")

    # Our masks, as the pipeline cached them. The tag is built exactly as the notebook
    # builds it, so a window that was run under a different length cannot be picked up here.
    tag = f"{args.label}_{int(start_s * 10)}_{int(duration_s * 10)}"
    cache = REPO / "cache" / f"masks_{tag}.npz"
    if not cache.exists():
        sys.exit(f"no cached masks at {cache.relative_to(REPO)}")

    rows = list(csv.DictReader(traj_path.open()))
    traj_t = np.array([float(r["time_s"]) for r in rows])

    vrs = sorted((REPO / "recordings").glob(f"{row['recording']}_*.vrs"))
    if not vrs:
        sys.exit(f"no recording matching {row['recording']}_*.vrs")

    # Our own detection over the window, from the same code the twelve recordings use.
    provider, first_ns, vio_ts, vio_mats = gfo.room_from_device(vrs[0])
    hands = gfo.hand_points_in_room(provider, first_ns, vio_ts, vio_mats)
    clouds = np.load(REPO / "outputs" / f"object_{args.label}_clouds.npz")
    raw, _which = gfo.nearest_distances(clouds, traj_t, hands)
    distance = gfo.smooth_median(raw, gfo.SMOOTH)
    ours = distance < gfo.CONTACT_CM

    # Our masks come back packed, so the frame size has to come from the recording to
    # unpack them. The first colour frame is the cheapest place to read it.
    rgb = provider.get_stream_id_from_label("camera-rgb")
    H, W = provider.get_image_data_by_index(rgb, 0)[0].to_numpy_array().shape[:2]
    z = np.load(cache)
    our_masks = [np.unpackbits(z[k])[: H * W].reshape(H, W).astype(bool) for k in sorted(z.files)]

    labels = json.loads((folder / "hand_object_interaction" /
                         "hand_object_interaction_results.json").read_text())
    contact = collections.defaultdict(list)
    for e in labels:
        if e["category_id"] == CONTACT_CATEGORY:
            contact[int(e["image_id"])].append(e)

    label_t = np.array(sorted((i * 1_000_000 - first_ns) / 1e9 for i in contact))
    label_id = {(i * 1_000_000 - first_ns) / 1e9: i for i in contact}

    agree = disagree = 0
    theirs_yes = ours_yes = both_yes = 0
    compared = []
    for k, t in enumerate(traj_t):
        if k >= len(our_masks) or np.isnan(distance[k]):
            continue
        ours_now = bool(ours[k])
        # Their labels run at 10 Hz and ours at 30, so a frame takes the label nearest it.
        # Beyond a twentieth of a second there is no label for this moment at all and a
        # frame with no contact label means they saw nobody touching anything.
        theirs_now = False
        if len(label_t):
            j = int(np.argmin(np.abs(label_t - t)))
            if abs(label_t[j] - t) <= 0.05:
                ours_px = our_masks[k]
                # Their mask is drawn on a smaller copy of the frame, so it is stretched to
                # ours by index before the two are compared. Nearest neighbour is right
                # here, since both sides are yes or no per pixel and smoothing a mask would
                # invent pixels that belong to neither object.
                for e in contact[label_id[label_t[j]]]:
                    m = decode(e).astype(bool)
                    yi = (np.arange(H) * m.shape[0] // H).clip(0, m.shape[0] - 1)
                    xi = (np.arange(W) * m.shape[1] // W).clip(0, m.shape[1] - 1)
                    big = m[np.ix_(yi, xi)]
                    if ours_px.sum() and (big & ours_px).sum() / ours_px.sum() >= MIN_OVERLAP:
                        theirs_now = True
                        break
        compared.append((t, ours_now, theirs_now))
        theirs_yes += theirs_now
        ours_yes += ours_now
        both_yes += ours_now and theirs_now
        if ours_now == theirs_now:
            agree += 1
        else:
            disagree += 1

    n = agree + disagree
    if not n:
        sys.exit("no frame could be compared")

    print(f"{args.label}, {start_s} to {start_s + duration_s} s of their recording")
    print(f"{n} frames compared\n")
    print(f"they mark our object in contact   : {theirs_yes / n * 100:5.1f}% of frames")
    print(f"we mark it in contact             : {ours_yes / n * 100:5.1f}% of frames")
    print(f"we agree                          : {agree / n * 100:5.1f}% of frames")
    if theirs_yes:
        print(f"of the frames they mark, we catch : {both_yes / theirs_yes * 100:5.1f}%")
    if ours_yes:
        print(f"of the frames we mark, they agree : {both_yes / ours_yes * 100:5.1f}%")

    # Where each side thinks the contact starts and stops, because a percentage can hide a
    # detection that is right about how much contact there was and wrong about when.
    def spans(flagged):
        out, start = [], None
        for (t, o, th), v in zip(compared, flagged):
            if v and start is None:
                start = t
            elif not v and start is not None:
                out.append((start, t)); start = None
        if start is not None:
            out.append((start, compared[-1][0]))
        return out

    ours_spans = spans([c[1] for c in compared])
    their_spans = spans([c[2] for c in compared])
    fmt = lambda s: ", ".join(f"{a:.2f} to {b:.2f}" for a, b in s) or "none"
    print(f"\nthey say contact over : {fmt(their_spans)}")
    print(f"we say contact over   : {fmt(ours_spans)}")

    dest = REPO / "outputs" / f"contact_vs_pilot_{args.label}.csv"
    with open(dest, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time_s", "ours", "theirs"])
        w.writerows([(round(t, 3), int(o), int(th)) for t, o, th in compared])
    print(f"\nwrote {dest.relative_to(REPO)}")


if __name__ == "__main__":
    main()
