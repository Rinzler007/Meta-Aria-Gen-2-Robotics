#!/usr/bin/env python3
"""Ask whether the shape of a hand can tell you that the hand is holding something.

Why ask. Our grip detection reads one number off the 21 hand landmarks, the flatness, and
splits each recording into holding and not holding. It agrees with our own twelve
recordings 91 per cent of the time. On somebody else's recording it scores 46.9 per cent,
which is guessing. See `tools/check_against_pilot.py` for that result.

Flatness could simply be the wrong number. The Pilot Dataset labels say, frame by frame,
whether a hand is in contact with an object, so every other number we can read off the
landmarks can be scored the same way. This runs that sweep.

The score is the chance that a randomly chosen holding frame reads higher than a randomly
chosen idle frame. Fifty per cent is guessing and a hundred is perfect separation. A number
below fifty is just as useful as the same distance above it, since you flip the comparison,
so we report whichever way round reads stronger.

Twelve features go in. Three come from the shape of the landmark cloud, three from how far
the landmarks sit from its middle and four from the distance between particular landmarks,
which is how far apart the fingers are. The twelfth is the volume the cloud fills.

Then the combination. Any one feature could be weak while several together are strong, so
we fit a straight line through all twelve. The fit uses the first half of the recording and
the score comes from the second half. Fitting and scoring on the same frames would let the
line memorise them and the gap between the two numbers tells you how much of that happened.

    python3 tools/grip_features.py reference/pilot_cook_0

It writes `outputs/grip_features.csv` with one row per feature and a row for the
combination.

What it found on `cook_0`. No single feature clears 59 per cent and most sit between 51 and
55. The combination reaches 59.1 per cent on the half it was fitted on. It falls to 50.5
per cent on the half it was not, so the line memorised the first half and learned nothing
that carries over.

What that means. The shape of a hand does not tell you whether it holds something. Our
twelve recordings are each one slow reach, grip, carry and release, so the hand changes
shape once in a way that is easy to find. In a kitchen the hand is constantly half closed
around something or nothing and the two cases look the same. Looking for a better hand
feature is a dead end and the signal has to come from the object. That is what
`tools/grip_from_object.py` does.
"""

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent

from projectaria_tools.core import data_provider

# Their label for an object a hand is touching, the same one `check_against_pilot.py` uses.
CONTACT_CATEGORY = 3

# A label carries the timestamp of its frame and the hand stream runs faster, so we take the
# nearest hand sample. Anything further away than this is a gap in the hand tracking and we
# drop the label. Pairing it with a sample from somewhere else would be worse.
MATCH_S = 0.05

# The names go in the output file, so they have to read as English.
NAMES = [
    "flatness, smallest spread over the total",
    "smallest spread over the largest",
    "middle spread over the largest",
    "mean distance from the middle",
    "largest distance from the middle",
    "spread of those distances",
    "how wide the hand reaches",
    "volume the landmarks fill",
    "thumb tip to index tip",
    "thumb tip to little finger tip",
    "wrist to index tip",
    "wrist to middle finger tip",
]


def features(lm):
    """Twelve numbers off one hand, using no labels and no knowledge of the object.

    The landmark cloud is centred first, so everything here describes the shape of the hand
    and none of it describes where the hand is. A hand held out in front of you and the same
    hand held by your side give the same twelve numbers, which is what we want, since the
    question is what the hand is doing and not where it is.
    """
    centred = lm - lm.mean(axis=0)
    # The eigenvalues of the covariance are the spread along the three natural axes of the
    # cloud, smallest first. A flat hand spreads in two directions and hardly at all in the
    # third, so the smallest one falling is what flatness is built on.
    ev = np.sort(np.linalg.eigvalsh(centred.T @ centred / len(centred)))
    dist = np.linalg.norm(centred, axis=1)
    return [
        float(ev[0] / ev.sum()),
        float(ev[0] / ev[2]),
        float(ev[1] / ev[2]),
        float(dist.mean()),
        float(dist.max()),
        float(dist.std()),
        float(np.sqrt(ev[2])),
        float(np.prod(np.sqrt(ev))),
        # The hand tracking does not label its landmarks, so these four indices are read off
        # the ordering the stream happens to use. They are the thumb tip, the index tip, the
        # middle tip and the little finger tip in that ordering.
        float(np.linalg.norm(lm[4] - lm[8])),
        float(np.linalg.norm(lm[4] - lm[20])),
        float(np.linalg.norm(lm[0] - lm[8])),
        float(np.linalg.norm(lm[0] - lm[12])),
    ]


def separation(high, low):
    """The chance a value drawn from `high` reads above one drawn from `low`, as a percentage.

    This is the area under the ROC curve and it is worth saying why we want it here. A
    threshold score would depend on where we put the threshold and we have no principled
    place to put one on somebody else's recording. This number asks the threshold-free
    question: are the holding frames higher than the idle ones at all ? If the answer is
    fifty per cent then no threshold anywhere can help, so the feature is finished.
    """
    both = np.concatenate([high, low])
    # Ranking and summing is the same as counting every winning pair. It costs one sort,
    # where comparing every pair against every other would cost a great deal more.
    rank = np.empty(len(both))
    rank[np.argsort(both)] = np.arange(len(both))
    wins = rank[: len(high)].sum() - len(high) * (len(high) - 1) / 2
    return wins / (len(high) * len(low)) * 100


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", help="a Pilot Dataset sequence folder, for eg. reference/pilot_cook_0")
    args = ap.parse_args()

    folder = Path(args.folder)
    vrs = next(folder.glob("*.vrs"), None)
    if vrs is None:
        sys.exit(f"no .vrs file in {folder}")
    labels = folder / "hand_object_interaction" / "hand_object_interaction_results.json"
    if not labels.exists():
        sys.exit(f"no interaction labels at {labels}")

    provider = data_provider.create_vrs_data_provider(str(vrs))
    rgb = provider.get_stream_id_from_label("camera-rgb")
    hands = provider.get_stream_id_from_label("handtracking")
    # Their label timestamps count from the first colour frame, so we need that one time to
    # put labels and hand samples on the same clock.
    first_ns = provider.get_image_data_by_index(rgb, 0)[1].capture_timestamp_ns

    # One label file holds many rows per frame, one per thing they saw. We only need to know
    # whether any row on a frame was a hand touching an object.
    seen = collections.defaultdict(set)
    for row in json.load(open(labels)):
        seen[int(row["image_id"])].add(row["category_id"])
    # The image id counts milliseconds, which cost us a wrong answer once before, so the
    # conversion to nanoseconds is written out in full here.
    held = {(i * 1_000_000 - first_ns) / 1e9: (CONTACT_CATEGORY in c) for i, c in seen.items()}

    # Read every hand sample once and keep the twelve features for each hand we got.
    samples = collections.defaultdict(dict)
    for i in range(provider.get_num_data(hands)):
        s = provider.get_hand_pose_data_by_index(hands, i)
        t = (s.tracking_timestamp.total_seconds() * 1e9 - first_ns) / 1e9
        for side in ("left", "right"):
            hand = s.right_hand if side == "right" else s.left_hand
            if hand is None:
                continue
            lm = np.asarray(hand.landmark_positions_device).reshape(-1, 3)
            # A partial hand would give features that are not comparable with a full one, so
            # we only keep samples where all 21 landmarks came through.
            if len(lm) == 21:
                samples[t][side] = features(lm)

    times = np.array(sorted(samples))
    rows, truth, when = [], [], []
    for label_t, is_held in sorted(held.items()):
        j = np.searchsorted(times, label_t)
        if j >= len(times) or abs(times[j] - label_t) > MATCH_S:
            continue
        # Their label says a hand is in contact and does not say which hand, so both hands on
        # that frame carry the same answer. That adds noise in one direction only: a frame
        # where one hand holds something contributes an idle hand labelled as holding. It
        # cannot invent separation that is not there, so a chance result stays a chance result.
        for side, f in samples[times[j]].items():
            rows.append(f)
            truth.append(1 if is_held else 0)
            when.append(label_t)

    X = np.array(rows)
    y = np.array(truth)
    when = np.array(when)
    if len(X) < 100:
        sys.exit("too few frames matched between the labels and the hand tracking")

    print(f"{len(X)} hand samples matched a label, {y.mean() * 100:.0f} per cent of them holding\n")

    out = [("feature", "separation_pct", "note")]
    print(f"{'feature':<42} {'score':>7}")
    for k, name in enumerate(NAMES):
        s = separation(X[y == 1, k], X[y == 0, k])
        # Flipping the comparison is free, so a feature that reads lower when holding is
        # exactly as good as one that reads higher by the same margin.
        flipped = s < 50
        score = max(s, 100 - s)
        note = "lower when holding" if flipped else ""
        print(f"{name:<42} {score:6.1f}%  {note}")
        out.append((name, f"{score:.1f}", note))

    # Now the combination. The split goes by time. Why not at random ? Because neighbouring frames
    # look almost the same and a random split would put a frame's near twin on the other
    # side. That would hand the fit the answer and the held-out score would be a fiction.
    half = np.median(when)
    train, test = when < half, when >= half
    # Standardising puts every feature on the same footing. Without it a distance in metres
    # and a ratio between zero and one would get weights that differ by a thousand and the
    # fit would be deciding on units.
    mu, sd = X[train].mean(axis=0), X[train].std(axis=0) + 1e-12
    Z = np.hstack([(X - mu) / sd, np.ones((len(X), 1))])
    # Least squares onto minus one and plus one. A logistic fit would give the same ordering
    # of frames and the score only looks at the ordering, so the simpler fit is enough.
    w = np.linalg.lstsq(Z[train], y[train] * 2.0 - 1.0, rcond=None)[0]
    score = Z @ w
    held_out = separation(score[test][y[test] == 1], score[test][y[test] == 0])
    in_sample = separation(score[train][y[train] == 1], score[train][y[train] == 0])

    print()
    print(f"{'all twelve together, on the half it was fitted on':<42} {in_sample:6.1f}%")
    print(f"{'all twelve together, on the other half':<42} {held_out:6.1f}%")
    out.append(("all twelve together, fitted half", f"{in_sample:.1f}", "memorised"))
    out.append(("all twelve together, held-out half", f"{held_out:.1f}", "the honest number"))

    print()
    if held_out < 55:
        print("No feature and no combination of them separates holding from idle on this")
        print("recording. The shape of a hand does not carry whether it is holding something.")
    else:
        print("A combination carries some signal. Worth building a detector on.")

    dest = REPO / "outputs" / "grip_features.csv"
    dest.parent.mkdir(exist_ok=True)
    with open(dest, "w", newline="") as fh:
        csv.writer(fh).writerows(out)
    print(f"\nwrote {dest.relative_to(REPO)}")


if __name__ == "__main__":
    main()
