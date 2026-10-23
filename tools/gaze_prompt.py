#!/usr/bin/env python3
"""Can where you are looking say which object the demonstration is about ?

The pipeline needs one pixel on the object before it can track anything and a person
reads that pixel off a frame and types it in. `tools/prompt_rule.py` tried to replace that
with a rule built from the hand and the best one lands on the object 39 per cent of the
time against a ceiling of 56. It fails two frames in three.

The glasses also record where the wearer is looking. That is a different kind of answer. A
hand tells you where something is being touched. Eyes tell you what the person is paying
attention to and when somebody picks a thing up they look at it first. So the gaze pixel
is a candidate for the prompt and this scores it against the same labels, in the same way,
so the two numbers can be put side by side.

    python3 tools/gaze_prompt.py reference/pilot_cook_0

What is being scored. The eye tracker gives a direction and, on Gen 2, a point in space
where the two eyes converge. Projecting that point into the colour camera gives a pixel.
We score that pixel, the same pixel at several fixed depths and the halfway points between
gaze and hand, since looking slightly past an object while reaching for it is the ordinary
case.

What it found on `cook_0`. Gaze on its own is poor. The pixel where the eyes converge lands
on the object 14.9 per cent of the time and pushing the same direction out to any fixed
distance makes no difference, staying at 15 per cent from 30 cm to 1.5 m. People do not
look at the middle of the thing in their hand.

Gaze together with the hand is the best rule this project has. Starting at the middle of
the hand and stepping a short way towards where the eyes are looking lands on the object
46.3 per cent of the time, against 39.6 per cent for the hand-only rule scored on the same
1,135 frames. The ceiling on those frames is 54 per cent, so the gaze rule reaches 86 per
cent of what is available where the hand alone reaches 73.

Why a small step and not a large one. Four centimetres scores 45.5 per cent and eight
scores 39.6, so going further towards the gaze point makes it worse. The gaze gives the
direction the object lies in. It does not give the distance, which the converged depth
confirms: it reads a median of 0.34 m, closer than the hand usually is.

This does not finish the job. It still misses more than half the frames, so the typed
coordinate stays. It does say the glasses carry a signal about which object matters that
the hand alone does not.
"""

import argparse
import collections
import json
from pathlib import Path

import numpy as np
from pycocotools import mask as cocomask
from projectaria_tools.core import data_provider
from projectaria_tools.core.mps import utils as mps_utils

HAND_CATEGORY = 1
CONTACT_CATEGORY = 3
# A sample has to be this close in time to a labelled frame to be paired with it.
MATCH_S = 0.05


def decode(entry):
    """Their masks are run length encoded, which `pycocotools` turns back into pixels."""
    seg = dict(entry["segmentation"])
    # The counts arrive as text out of JSON and the decoder wants bytes.
    if isinstance(seg["counts"], str):
        seg["counts"] = seg["counts"].encode()
    return cocomask.decode(seg)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", help="a Pilot Dataset sequence folder")
    args = ap.parse_args()

    folder = Path(args.folder)
    vrs = sorted(folder.glob("*.vrs"))
    if not vrs:
        raise SystemExit(f"no recording in {folder}")

    p = data_provider.create_vrs_data_provider(str(vrs[0]))
    rgb = p.get_stream_id_from_label("camera-rgb")
    hid = p.get_stream_id_from_label("handtracking")
    gid = p.get_stream_id_from_label("eyegaze")
    first = p.get_image_data_by_index(rgb, 0)[1].capture_timestamp_ns
    cal = p.get_device_calibration()
    rgb_cal = cal.get_camera_calib("camera-rgb")
    T_device_rgb = cal.get_transform_device_sensor("camera-rgb")

    labels = json.loads((folder / "hand_object_interaction" /
                         "hand_object_interaction_results.json").read_text())
    held, hands_lbl = collections.defaultdict(list), collections.defaultdict(list)
    for e in labels:
        if e["category_id"] == CONTACT_CATEGORY:
            held[int(e["image_id"])].append(e)
        elif e["category_id"] == HAND_CATEGORY:
            hands_lbl[int(e["image_id"])].append(e)
    if not held:
        raise SystemExit("no contact labels in this sequence")

    # Their frames were scaled down before anybody drew on them, so a pixel projected at the
    # camera's own size has to be scaled the same way before it can be compared.
    scale = decode(next(iter(held.values()))[0]).shape[1] / rgb_cal.get_image_size()[0]

    def project_device(point):
        """A point in the device frame to a pixel in their label coordinates."""
        q = T_device_rgb.inverse() @ point
        # Behind the camera there is no pixel and projecting anyway would fold the point
        # round to the opposite side of the image and score it as a hit somewhere random.
        if q[2] <= 0:
            return None
        px = rgb_cal.project(q)
        return None if px is None else np.array([px[0], px[1]]) * scale

    # Read the gaze stream once. Each sample carries both a direction and, on Gen 2, the
    # point in space where the two eyes converge, which is what makes a depth available at
    # all without us guessing one.
    gaze_t, gaze = [], []
    for i in range(p.get_num_data(gid)):
        g = p.get_eye_gaze_data_by_index(gid, i)
        if not g.combined_gaze_valid:
            continue
        gaze_t.append((g.tracking_timestamp.total_seconds() * 1e9 - first) / 1e9)
        gaze.append(g)
    if not gaze:
        raise SystemExit("no valid eye gaze in this recording")
    gaze_t = np.array(gaze_t)

    # And the hands, so the rules that mix the two have something to mix.
    hand_t, hand_lm = [], []
    for i in range(p.get_num_data(hid)):
        s = p.get_hand_pose_data_by_index(hid, i)
        t = (s.tracking_timestamp.total_seconds() * 1e9 - first) / 1e9
        for side in ("left", "right"):
            h = s.right_hand if side == "right" else s.left_hand
            if h is None:
                continue
            lm = np.asarray(h.landmark_positions_device).reshape(-1, 3)
            if len(lm) == 21:
                hand_t.append(t)
                hand_lm.append(lm)
    hand_t = np.array(hand_t)

    def inside(px, masks):
        if px is None:
            return False
        x, y = int(round(px[0])), int(round(px[1]))
        return any(0 <= y < m.shape[0] and 0 <= x < m.shape[1] and m[y, x] for m in masks)

    hit = collections.Counter()
    total = checked = on_hand = 0
    gaze_depths = []

    for img_id, entries in held.items():
        t = (img_id * 1_000_000 - first) / 1e9
        gj = int(np.argmin(np.abs(gaze_t - t)))
        if abs(gaze_t[gj] - t) > MATCH_S:
            continue
        g = gaze[gj]
        masks = [decode(e) for e in entries]
        total += 1

        # The ceiling, measured the same way `tools/prompt_rule.py` measures it, so the two
        # tools report the same number for the same thing. It says how often any method at
        # all could succeed, given that the tracking and the labels do not perfectly agree.
        hj = int(np.argmin(np.abs(hand_t - t))) if len(hand_t) else None
        if hj is not None and abs(hand_t[hj] - t) <= MATCH_S and img_id in hands_lbl:
            checked += 1
            on_hand += inside(project_device(hand_lm[hj].mean(axis=0)),
                              [decode(e) for e in hands_lbl[img_id]])

        # The gaze as the tracker reports it, converged point and all. This is the rule that
        # needs no hand at all, which is the one worth having.
        px = mps_utils.get_gaze_vector_reprojection(
            g, "camera-rgb", cal, rgb_cal, depth_m=float(g.depth))
        if px is not None:
            hit["where the eyes converge"] += inside(np.array(px) * scale, masks)
        if g.spatial_gaze_point_valid:
            gaze_depths.append(float(g.depth))

        # The same direction pushed out to fixed distances. If the converged depth is
        # unreliable then one of these will beat it and if it is reliable none will.
        for d in (0.3, 0.5, 0.7, 1.0, 1.5):
            px = mps_utils.get_gaze_vector_reprojection(g, "camera-rgb", cal, rgb_cal, depth_m=d)
            if px is not None:
                hit[f"along the gaze at {d:.1f} m"] += inside(np.array(px) * scale, masks)

        # Gaze and hand together. Somebody reaching for a thing looks at it and touches it,
        # so the object tends to sit between the two. Walking from the hand towards the
        # gaze point asks how far along that line the object actually is.
        if hj is not None and abs(hand_t[hj] - t) <= MATCH_S:
            # The hand-only rule that `tools/prompt_rule.py` found to be the best of its
            # kind, scored here as well. It is the number the gaze rules have to beat, and
            # scoring it on these exact frames is the only way the comparison is fair. The
            # two tools match different frames, since this one also needs a gaze sample, so
            # quoting the other tool's figure would be comparing two different sets.
            lm = hand_lm[hj]
            c = lm.mean(axis=0)
            d = np.linalg.norm(lm - c, axis=1)
            outer = lm[np.argsort(d)[-5:]].mean(axis=0) - c
            if np.linalg.norm(outer) > 1e-6:
                hit["hand only, 2 cm towards the outer landmarks"] += inside(
                    project_device(c + outer / np.linalg.norm(outer) * 0.02), masks)

        if hj is not None and abs(hand_t[hj] - t) <= MATCH_S and g.spatial_gaze_point_valid:
            centre = hand_lm[hj].mean(axis=0)
            # The converged point is given in the central pupil frame, so it has to be
            # carried into the device frame before it can be mixed with the landmarks.
            T_device_cpf = cal.get_transform_device_cpf()
            # The transform hands back a column, so it is flattened before it is treated
            # as a point alongside the landmark centre.
            look = np.asarray(T_device_cpf @ np.asarray(g.spatial_gaze_point_in_cpf)).ravel()[:3]
            for f in (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75):
                hit[f"{int(f * 100)}% of the way from hand to gaze"] += inside(
                    project_device(centre + (look - centre) * f), masks)

            # The same direction but a fixed step in centimetres. A fraction depends on how
            # far away the person is looking, so the same fraction means four centimetres
            # when they look at their hands and forty when they look across the room. A
            # step in centimetres means the same thing wherever they are looking, which is
            # what you want from a rule that has to work on a recording nobody has checked.
            v = look - centre
            n = np.linalg.norm(v)
            if n > 1e-6:
                for cm in (1, 2, 3, 4, 6, 8):
                    hit[f"{cm} cm from the hand towards the gaze"] += inside(
                        project_device(centre + v / n * (cm / 100)), masks)

    if not total:
        raise SystemExit("no labelled frame lined up with a gaze sample")

    print(f"scored on {total} frames where a gaze sample and a labelled held object line up")
    if checked:
        print(f"ceiling: the hand's own middle lands on the labelled hand "
              f"{on_hand / checked * 100:.0f}% of {checked} frames")
    if gaze_depths:
        print(f"the eyes converged at a median of {np.median(gaze_depths):.2f} m")
    print()
    for name, n in hit.most_common():
        print(f"  {n / total * 100:5.1f}%  {name}")

    # The best rule that used the gaze, which is the thing being tested. The hand-only
    # baseline is excluded here because it is what we are comparing against.
    gaze_rules = {k: v for k, v in hit.items() if not k.startswith("hand only")}
    best_name, best_n = max(gaze_rules.items(), key=lambda kv: kv[1])
    best = best_n / total * 100
    baseline = hit["hand only, 2 cm towards the outer landmarks"] / total * 100
    print()
    print(f"best gaze rule  : {best:5.1f} per cent, on {best_name}")
    print(f"hand only       : {baseline:5.1f} per cent, on the same {total} frames")
    if checked:
        ceiling = on_hand / checked * 100
        print(f"ceiling         : {ceiling:5.1f} per cent")
        print()
        print(f"The gaze rule reaches {best / ceiling * 100:.0f} per cent of what is available "
              f"where the hand alone reaches {baseline / ceiling * 100:.0f}.")
    print("Neither replaces the typed coordinate. Both are worth more than guessing.")


if __name__ == "__main__":
    main()
