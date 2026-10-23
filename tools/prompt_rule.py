#!/usr/bin/env python3
"""Score ways of guessing where the object is, using somebody else's labels.

The pipeline needs one pixel on the object. A person reads it off a frame and types it in,
which is the last manual step. Any rule for placing it automatically needs a correct answer
to be scored against. None of our own recordings has one.

Meta's Aria Gen 2 Pilot Dataset does. Its `hand_object_interaction` labels mark the object
a hand is touching, frame by frame, so a rule can propose a pixel and be asked whether it
lands inside that object.

Every rule here is built from the 21 hand landmarks alone. The glasses never say which
landmark is which, so nothing may depend on knowing a fingertip from a knuckle.

    python3 tools/prompt_rule.py reference/pilot_cook_0

What it finds on `cook_0`. Taking the middle of the hand and stepping 1 to 2 cm towards the
points furthest from that middle lands inside the object 39 per cent of the time. The
middle of the hand on its own gets 38 per cent. Stepping further out gets steadily worse,
reaching 5 per cent at 9 cm, so the old idea of reaching past the fingertips to find the
object is wrong. A held object overlaps the hand holding it.

Read 39 per cent against a ceiling rather than against 100. The hand's own middle lands on
the labelled hand only 56 per cent of the time, because hand tracking and labels disagree
and because a hand is often half hidden behind what it holds. So the rule reaches roughly
seventy per cent of what is available. It still fails two frames in three.
"""

import argparse
import collections
import json
from pathlib import Path

import numpy as np
from pycocotools import mask as cocomask
from projectaria_tools.core import data_provider

HAND_CATEGORY = 1
CONTACT_CATEGORY = 3
# A hand sample has to be this close in time to a labelled frame to be paired with it.
MATCH_S = 0.05


def rules(lm):
    """Candidate pixels in the device frame, each built from the 21 landmarks alone."""
    c = lm.mean(axis=0)
    d = np.linalg.norm(lm - c, axis=1)
    far = lm[np.argsort(d)[-5:]].mean(axis=0)
    out = {"middle of the hand": c, "median of the landmarks": np.median(lm, axis=0)}
    v = far - c
    n = np.linalg.norm(v)
    if n > 1e-6:
        for cm in (-2, -1, 1, 2, 3, 6, 9):
            out[f"{cm:+d} cm towards the outer landmarks"] = c + v / n * (cm / 100)
    # Towards the glasses, since a held object sits between the hand and the wearer.
    towards = -c / (np.linalg.norm(c) + 1e-9)
    for cm in (2, 4):
        out[f"{cm:+d} cm towards the glasses"] = c + towards * (cm / 100)
    return out


def decode(entry):
    seg = dict(entry["segmentation"])
    if isinstance(seg["counts"], str):
        seg["counts"] = seg["counts"].encode()
    return cocomask.decode(seg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    a = ap.parse_args()
    folder = Path(a.folder)
    vrs = sorted(folder.glob("*.vrs"))
    if not vrs:
        raise SystemExit(f"no recording in {folder}")

    p = data_provider.create_vrs_data_provider(str(vrs[0]))
    rgb = p.get_stream_id_from_label("camera-rgb")
    hid = p.get_stream_id_from_label("handtracking")
    first = p.get_image_data_by_index(rgb, 0)[1].capture_timestamp_ns
    cal = p.get_device_calibration()
    rgb_cal = cal.get_camera_calib("camera-rgb")
    T = cal.get_transform_device_sensor("camera-rgb")

    labels = json.loads((folder / "hand_object_interaction" /
                         "hand_object_interaction_results.json").read_text())
    held = collections.defaultdict(list)
    hands_lbl = collections.defaultdict(list)
    for e in labels:
        if e["category_id"] == CONTACT_CATEGORY:
            held[int(e["image_id"])].append(e)
        elif e["category_id"] == HAND_CATEGORY:
            hands_lbl[int(e["image_id"])].append(e)

    # The labels were drawn on frames scaled down from the camera's own size, so a
    # projected pixel is scaled the same way before being compared against them.
    any_mask = decode(next(iter(held.values()))[0])
    scale = any_mask.shape[1] / rgb_cal.get_image_size()[0]

    def project(p_dev):
        q = T.inverse() @ p_dev
        if q[2] <= 0:
            return None
        px = rgb_cal.project(q)
        return None if px is None else (np.array([px[0], px[1]]) * scale)

    samples = []
    for i in range(p.get_num_data(hid)):
        s = p.get_hand_pose_data_by_index(hid, i)
        t = (s.tracking_timestamp.total_seconds() * 1e9 - first) / 1e9
        for side in ("left", "right"):
            hh = s.right_hand if side == "right" else s.left_hand
            if hh is None:
                continue
            lm = np.asarray(hh.landmark_positions_device).reshape(-1, 3)
            if len(lm) == 21:
                samples.append((t, lm))
    samples.sort(key=lambda x: x[0])
    st = np.array([x[0] for x in samples])

    def inside(px, masks):
        if px is None:
            return False
        x, y = int(round(px[0])), int(round(px[1]))
        return any(0 <= y < m.shape[0] and 0 <= x < m.shape[1] and m[y, x] for m in masks)

    hit = collections.Counter()
    total = on_hand = checked = 0
    for img_id, entries in held.items():
        t = (img_id * 1_000_000 - first) / 1e9
        j = int(np.argmin(np.abs(st - t)))
        if abs(st[j] - t) > MATCH_S:
            continue
        masks = [decode(e) for e in entries]
        total += 1
        lm = samples[j][1]
        if img_id in hands_lbl:
            checked += 1
            on_hand += inside(project(lm.mean(axis=0)), [decode(e) for e in hands_lbl[img_id]])
        for name, pt in rules(lm).items():
            hit[name] += inside(project(pt), masks)

    if not total:
        raise SystemExit("no labelled frame lined up with a hand sample")

    print(f"scored on {total} frames where a hand and a labelled held object line up")
    print(f"ceiling: the hand's own middle lands on the labelled hand {on_hand/checked*100:.0f}% "
          f"of {checked} frames\n")
    for name, n in hit.most_common():
        print(f"  {n/total*100:5.1f}%  {name}")
    best = hit.most_common(1)[0]
    print(f"\nbest rule reaches {best[1]/total*100:.0f}%, which is "
          f"{best[1]/total/(on_hand/checked)*100:.0f}% of the ceiling. It still misses two "
          f"frames in three, so the coordinate stays manual.")


if __name__ == "__main__":
    main()
