#!/usr/bin/env python3
"""Check the grip detection against somebody else's labels.

Everything this project measures is measured against itself. The grip detection was scored
against windows chosen by eye in the same lab, by the same person, on the same twelve
recordings. That is worth something and it is not independent.

Meta's Aria Gen 2 Pilot Dataset gives an outside answer. It was recorded on the same
glasses in somebody else's kitchen. Its `hand_object_interaction` labels mark, frame by
frame, the object a hand is in contact with. Those labels owe nothing to this project.

What this does. It runs the same grip detection on one of their recordings, then asks how
often it agrees with their labels. A frame counts as holding when the labels carry an
object in contact with a hand, which is their category 3, sitting a median of 151 px from
the hand with 0.17 overlap while everything else sits 381 px away with none.

    python3 tools/check_against_pilot.py reference/pilot_cook_0

The folder needs the recording and the interaction labels from one sequence. Downloads come
from a manifest off Meta's dataset page, since the links are signed and expire.

What it says about `cook_0`. The grip detection does not survive the trip. Their labels mark
a held object in 1,244 of 2,959 frames, which is 42 per cent. Our detection marks 49 per
cent of the recording and agrees with them 46.9 per cent of the time, which is what you get
by guessing. Running it on the left hand instead gives 47.5 per cent.

Two numbers say why. The flatness levels separate by 0.056 on their recording against 0.073
to 0.144 on ours, so the signal is weaker. It comes out as 85 separate stretches where our
recordings each give one, so it is chattering rather than finding a demonstration.

The honest reading is that the method was built on twelve deliberate bench tasks where an
object is picked up, carried and set down. Cooking is continuous two handed work with many
brief contacts. The method has nothing to say about it. The 91 per cent agreement it
scores on our recordings is agreement with our own data.
"""

import argparse
import collections
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from projectaria_tools.core import data_provider

import importlib.util
_spec = importlib.util.spec_from_file_location("gi", REPO / "tools" / "grasp_intervals.py")
gi = importlib.util.module_from_spec(_spec)
_argv, sys.argv = sys.argv, ["grasp_intervals"]
_spec.loader.exec_module(gi)
sys.argv = _argv

# Their label for an object a hand is touching.
CONTACT_CATEGORY = 3


def labelled_contact(folder, first_ns):
    """Seconds from the first colour frame at which their labels say a hand holds something."""
    f = folder / "hand_object_interaction" / "hand_object_interaction_results.json"
    entries = json.loads(f.read_text())
    seen = collections.defaultdict(set)
    for e in entries:
        seen[int(e["image_id"])].add(e["category_id"])
    held, idle = [], []
    for img_id, cats in seen.items():
        # image_id is the capture time in milliseconds, on the same clock the
        # recording's own timestamps use.
        t = (img_id * 1_000_000 - first_ns) / 1e9
        (held if CONTACT_CATEGORY in cats else idle).append(t)
    return np.sort(np.array(held)), np.sort(np.array(idle))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="a downloaded pilot sequence")
    a = ap.parse_args()
    folder = Path(a.folder)

    vrs = sorted(folder.glob("*.vrs"))
    if not vrs:
        raise SystemExit(f"no recording in {folder}")

    p = data_provider.create_vrs_data_provider(str(vrs[0]))
    rgb = p.get_stream_id_from_label("camera-rgb")
    first_ns = p.get_image_data_by_index(rgb, 0)[1].capture_timestamp_ns

    held_t, idle_t = labelled_contact(folder, first_ns)
    print(f"their labels: {len(held_t)} frames holding, {len(idle_t)} frames not")

    got = gi.spread_series(vrs[0])
    if got is None:
        raise SystemExit("no hand tracked in that recording")
    side, ts, raw, sm = got
    cut, lo, hi = gi.two_levels(sm)
    gap = hi - lo
    print(f"our detection: acting hand {side}, flatness {lo:.3f} to {hi:.3f}, gap {gap:.3f}")
    if gap < gi.MIN_GAP:
        print("gap too small to call, nothing to compare")
        return

    ivs = gi.intervals(ts, sm, cut, gap)
    inside = np.zeros(len(ts), bool)
    for s, e in ivs:
        inside |= (ts >= s) & (ts <= e)

    def ours_says_held(times):
        """What our detection says at each of their labelled moments."""
        if not len(times):
            return np.array([], bool)
        j = np.clip(np.searchsorted(ts, times), 0, len(ts) - 1)
        return inside[j]

    on_held = ours_says_held(held_t)
    on_idle = ours_says_held(idle_t)
    # Of the frames they say are holding, how many do we also say are holding.
    recall = on_held.mean() * 100 if len(on_held) else float("nan")
    # Of the frames they say are not, how many do we correctly leave alone.
    reject = (1 - on_idle.mean()) * 100 if len(on_idle) else float("nan")
    agree = (on_held.sum() + (~on_idle).sum()) / (len(on_held) + len(on_idle)) * 100

    print()
    print(f"  they say holding, we agree      : {recall:5.1f}%")
    print(f"  they say not holding, we agree  : {reject:5.1f}%")
    print(f"  agreement over every frame      : {agree:5.1f}%")
    print()
    print(f"  we mark {len(ivs)} stretch{'es' if len(ivs) != 1 else ''}, "
          f"{inside.mean() * 100:.0f}% of the recording")
    print(f"  they mark {len(held_t) / (len(held_t) + len(idle_t)) * 100:.0f}% of their "
          f"labelled frames")


if __name__ == "__main__":
    main()
