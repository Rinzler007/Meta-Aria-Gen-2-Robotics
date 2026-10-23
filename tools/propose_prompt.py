#!/usr/bin/env python3
"""Propose the prompt coordinate for each of our own recordings, from the hand and the eyes.

The pipeline needs one pixel on the object and a person types it in. `tools/prompt_rule.py`
and `tools/gaze_prompt.py` settle which rule is best by scoring candidates against Meta's
labels. The winner starts at the middle of the hand and steps a short way towards where
the wearer is looking. This applies that winner to our twelve recordings so the rule can be
looked at on our own data. Until now it had only been seen on somebody else's.

    python3 tools/propose_prompt.py
    python3 tools/propose_prompt.py pour_01 scoop_02
    python3 tools/propose_prompt.py --sheet        # also draw the proposals on the frames

There is no labelled answer in our recordings. There is something nearly as good. The
pipeline cached the mask it produced from the typed coordinate, which is the object a person
picked out, so we can ask whether the proposed pixel lands inside that mask. That is the
question the pipeline actually cares about, since any pixel on the object does the job and
being near the typed one counts for nothing on its own.

The distance to the typed coordinate is reported alongside. A proposal far away is worth
looking at on the contact sheet before deciding which of the two is wrong, since a person
reads the pixel off a plotted frame and can be careless about where on the object it sits.

It writes `outputs/proposed_prompts.csv`. The pipeline still reads `tools/object_runs.csv`,
so nothing here changes a run until somebody copies a number across.

What it does on our twelve. The proposal lands inside the chosen object's mask in 4 of the
13 windows and sits a median of 95 px from the typed coordinate, in a frame 2016 px across.
All three soup tins hit. No spoon does.

The contact sheet says why and it is more encouraging than 4 of 13 sounds. The proposal
lands on the thing being handled in almost every window. Where the target is a spoon
sitting in a bowl of cereal, it lands on the bowl. A tin is the whole object in the hand and
a spoon is a thin stick inside something larger, so the rule finds the right place and picks
the wrong object out of it. Run with `--sheet` and look.

That is the remaining distance between this and dropping the person. Finding where the work
is happening is solved well enough. Choosing which of the things there is the object is not.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

from projectaria_tools.core import data_provider
from projectaria_tools.core.sensor_data import TimeDomain, TimeQueryOptions

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "outputs"
RECORDINGS = REPO / "recordings"
RUNS = REPO / "tools" / "object_runs.csv"
CACHE = REPO / "cache"

# How far to step from the middle of the hand towards where the eyes are looking. Four
# centimetres is what scored best among the fixed steps on Meta's labels, at 45.5 per cent
# against 39.6 for the hand on its own. A fraction of the way to the gaze point scored a
# whisker higher at 46.3. A fixed step is used here because it means the same thing
# whether the wearer is looking at their hands or across the room.
STEP_CM = 4.0

# A hand sample and a gaze sample have to be this close in time to the frame to be used.
MATCH_S = 0.05


def propose(vrs, t_s):
    """The pixel this rule proposes on the frame at `t_s`, with what it was built from."""
    p = data_provider.create_vrs_data_provider(str(vrs))
    rgb = p.get_stream_id_from_label("camera-rgb")
    hid = p.get_stream_id_from_label("handtracking")
    gid = p.get_stream_id_from_label("eyegaze")
    first = p.get_image_data_by_index(rgb, 0)[1].capture_timestamp_ns
    cal = p.get_device_calibration()
    rgb_cal = cal.get_camera_calib("camera-rgb")
    T_device_rgb = cal.get_transform_device_sensor("camera-rgb")
    T_device_cpf = cal.get_transform_device_cpf()

    # The hand nearest the moment we care about. Both hands are considered and the one
    # whose middle sits nearest the gaze point wins, since that is the hand doing the work.
    best = None
    for i in range(p.get_num_data(hid)):
        s = p.get_hand_pose_data_by_index(hid, i)
        t = (s.tracking_timestamp.total_seconds() * 1e9 - first) / 1e9
        if abs(t - t_s) > MATCH_S:
            continue
        for side in ("left", "right"):
            h = s.right_hand if side == "right" else s.left_hand
            if h is None:
                continue
            lm = np.asarray(h.landmark_positions_device).reshape(-1, 3)
            if len(lm) == 21:
                best = (side, lm.mean(axis=0))
    if best is None:
        return None

    look = None
    for i in range(p.get_num_data(gid)):
        g = p.get_eye_gaze_data_by_index(gid, i)
        t = (g.tracking_timestamp.total_seconds() * 1e9 - first) / 1e9
        if abs(t - t_s) > MATCH_S or not g.combined_gaze_valid:
            continue
        if g.spatial_gaze_point_valid:
            look = np.asarray(T_device_cpf @ np.asarray(g.spatial_gaze_point_in_cpf)).ravel()[:3]
    side, centre = best

    if look is None:
        # No usable gaze on this frame, so we fall back to the hand alone. That is the
        # weaker rule and the output says so, because a row that quietly used a different
        # rule would be worse than no row.
        point, used = centre, "hand only"
    else:
        v = look - centre
        n = np.linalg.norm(v)
        point = centre + v / n * (STEP_CM / 100) if n > 1e-6 else centre
        used = "hand and gaze"

    q = T_device_rgb.inverse() @ point
    # Behind the camera there is no pixel at all. Projecting anyway would fold the
    # point round to the far side of the image and read as a confident wrong answer.
    if q[2] <= 0:
        return None
    px = rgb_cal.project(q)
    if px is None:
        return None
    # The pipeline works in the frame's own pixels. Our colour frames come out 2016 wide
    # while the calibration describes the full 2560 wide sensor, so the projection is
    # scaled to the frames the notebook will actually see.
    frame = p.get_image_data_by_time_ns(
        rgb, first + int(t_s * 1e9), TimeDomain.DEVICE_TIME, TimeQueryOptions.CLOSEST)[0]
    scale = frame.to_numpy_array().shape[1] / rgb_cal.get_image_size()[0]
    return np.array([px[0], px[1]]) * scale, side, used


def on_object(label, row, px):
    """Does the proposed pixel land inside the mask the typed coordinate produced ?

    The pipeline caches the masks it propagated through each window. The first of them
    is the object as it stood in the frame the coordinate was read off. That mask is the
    closest thing our own recordings have to a correct answer, since a person looked at the
    frame and chose that object.

    Returns "yes" or "no". An empty string comes back when the window has never been run, which is
    the honest answer for a recording with no cache behind it.
    """
    start_s = float(row["start_s"])
    duration_s = float(row.get("duration_s") or 4.0)
    # The tag is built exactly as the notebook builds it, so a cache belonging to a
    # different window cannot be picked up by accident.
    cache = CACHE / f"masks_{label}_{int(start_s * 10)}_{int(duration_s * 10)}.npz"
    if not cache.exists():
        # Caches made before the window length joined the tag are named after the start
        # alone. Only the first frame is read here and that frame sits at the start of the
        # window whatever the window's length, so an older cache answers this question just
        # as well. A cache made for a different start would not and cannot match this name.
        cache = CACHE / f"masks_{label}_{int(start_s * 10)}.npz"
    if not cache.exists():
        return ""
    z = np.load(cache)
    first_key = sorted(z.files)[0]
    packed = z[first_key]
    # The mask was stored as packed bits with no shape beside it, so the frame's own size
    # has to come from the recording. Our colour frames are 2016 by 1512.
    vrs = sorted(RECORDINGS.glob(f"{row['recording']}_*.vrs"))
    p = data_provider.create_vrs_data_provider(str(vrs[0]))
    rgb = p.get_stream_id_from_label("camera-rgb")
    H, W = p.get_image_data_by_index(rgb, 0)[0].to_numpy_array().shape[:2]
    mask = np.unpackbits(packed)[: H * W].reshape(H, W).astype(bool)
    x, y = int(round(px[0])), int(round(px[1]))
    if not (0 <= x < W and 0 <= y < H):
        return "no"
    return "yes" if mask[y, x] else "no"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("only", nargs="*", help="labels to run; default is all of them")
    ap.add_argument("--sheet", action="store_true",
                    help="draw each proposal and the typed coordinate on its frame, into cache/")
    args = ap.parse_args()

    rows = []
    for r in csv.DictReader(RUNS.open()):
        label = r.get("label") or r["recording"]
        if args.only and label not in args.only:
            continue
        vrs = sorted(RECORDINGS.glob(f"{r['recording']}_*.vrs"))
        if not vrs:
            print(f"{label:<16} no recording, skipped")
            continue
        t_s = float(r["start_s"])
        got = propose(vrs[0], t_s)
        typed = np.array([float(r["prompt_x"]), float(r["prompt_y"])])
        if got is None:
            print(f"{label:<16} no hand or no gaze at {t_s} s, nothing proposed")
            continue
        px, side, used = got
        gap = float(np.linalg.norm(px - typed))
        on = on_object(label, r, px)
        rows.append({"label": label, "time_s": t_s,
                     "proposed_x": int(round(px[0])), "proposed_y": int(round(px[1])),
                     "typed_x": int(typed[0]), "typed_y": int(typed[1]),
                     "gap_px": round(gap, 1), "on_object": on, "hand": side, "rule": used})
        mark = {"yes": "on the object", "no": "misses", "": "no cached mask"}[on]
        print(f"{label:<16} proposes [{px[0]:6.0f}, {px[1]:6.0f}]   "
              f"typed [{typed[0]:6.0f}, {typed[1]:6.0f}]   {gap:5.0f} px apart   "
              f"{mark:<14} {side}, {used}")

    if not rows:
        sys.exit("nothing proposed")

    gaps = np.array([r["gap_px"] for r in rows])
    judged = [r for r in rows if r["on_object"]]
    hits = sum(1 for r in judged if r["on_object"] == "yes")
    print()
    if judged:
        print(f"lands on the object somebody picked : {hits} of {len(judged)} windows")
    print(f"distance from the typed coordinate  : median {np.median(gaps):.0f} px, "
          f"worst {gaps.max():.0f} px, in a frame 2016 px across")

    dest = OUT / "proposed_prompts.csv"
    with open(dest, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {dest.relative_to(REPO)}")

    if args.sheet:
        draw(rows)


def draw(rows):
    """Draw each proposal next to the typed coordinate, so they can be judged by eye."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    runs = {(r.get("label") or r["recording"]): r for r in csv.DictReader(RUNS.open())}
    n = len(rows)
    cols = 4
    fig, axes = plt.subplots((n + cols - 1) // cols, cols, figsize=(5 * cols, 4 * ((n + cols - 1) // cols)))
    for ax, row in zip(np.atleast_1d(axes).ravel(), rows):
        rec = runs[row["label"]]["recording"]
        vrs = sorted(RECORDINGS.glob(f"{rec}_*.vrs"))[0]
        p = data_provider.create_vrs_data_provider(str(vrs))
        rgb = p.get_stream_id_from_label("camera-rgb")
        first = p.get_image_data_by_index(rgb, 0)[1].capture_timestamp_ns
        img = p.get_image_data_by_time_ns(
            rgb, first + int(row["time_s"] * 1e9), TimeDomain.DEVICE_TIME,
            TimeQueryOptions.CLOSEST)[0].to_numpy_array()
        ax.imshow(img)
        ax.plot(row["typed_x"], row["typed_y"], "x", color="red", ms=14, mew=3)
        ax.plot(row["proposed_x"], row["proposed_y"], "+", color="lime", ms=16, mew=3)
        ax.set_title(f"{row['label']}  {row['gap_px']:.0f} px apart", fontsize=10)
        ax.set_xticks([]); ax.set_yticks([])
    for ax in np.atleast_1d(axes).ravel()[n:]:
        ax.axis("off")
    CACHE.mkdir(exist_ok=True)
    dest = CACHE / "proposed_prompts.png"
    # Saved before anything shows it, since showing a figure closes it and a savefig after
    # that writes a blank white image.
    plt.tight_layout()
    plt.savefig(dest, dpi=80)
    plt.close(fig)
    print(f"wrote {dest.relative_to(REPO)}: red cross typed, green plus proposed")


if __name__ == "__main__":
    main()
