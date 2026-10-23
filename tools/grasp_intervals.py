#!/usr/bin/env python3
"""Find when a hand closes on something and when it lets go, from hand spread alone.

A recording is one long clip and only part of it is the task. The rest is reaching,
settling and tidying. Bracketing the task automatically is what would let a caregiver
record all day without somebody watching each clip afterwards.

The glasses report 21 landmarks per hand and do not say which is which, so the fingertips
cannot be identified. The spread of those 21 points about their own centre needs no
labels. A hand closed around a spoon handle is a more compact set of points than an open
hand, so the spread drops on a grasp and rises on a release.

What it cannot do, and why. The feature separates a tight grip from an open hand. It does
not separate holding a wide object from reaching for one, because the hand is nearly the
same shape either way. Measured across the three tin recordings, the hand reads 4.8 to 5.3
while reaching and 4.4 to 5.3 while holding, which is no gap at all. It then drops to about
4.3 once the tin is set down and the hand relaxes.

So on a wide object the only clear transition in the signal is the release, and a method
looking for a change would mark the relaxed period afterwards as the grip. The gap
threshold below rejects those recordings before that answer is reported, which is the right
outcome reached for a reason worth knowing: the signal is ambiguous rather than inverted.

Covering wide objects needs something besides the shape of the hand, since by this measure
a hand about to pick a tin up and a hand carrying one look alike.

    python3 tools/grasp_intervals.py
    python3 tools/grasp_intervals.py scoop_01 pour_02

It writes `outputs/grasp_intervals.csv` and `outputs/grasp_intervals.png`.
"""

import argparse
import csv
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from projectaria_tools.core import data_provider

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "outputs"
RECORDINGS = REPO / "recordings"
RUNS = REPO / "tools" / "object_runs.csv"

# Hand poses arrive at 30 Hz, so this averages over about a third of a second. We want a
# change that lasts rather than a single sample dip and a grasp is not that quick.
SMOOTH = 9

# Below this the two levels are too close together to call. The line is drawn from our
# twelve recordings, where the spoon and the jug separate by 1.05 cm or more while the tin
# manages at most 0.98, so it is a rough guide rather than a calibrated threshold and
# pick_01 sits close enough to it to prove the point.
MIN_GAP_CM = 1.0

# An interval shorter than this is not a demonstration of anything. It is the hand passing
# through a posture on its way somewhere else.
MIN_HOLD_S = 0.5


def spread_series(vrs):
    """Spread of the 21 landmarks about their own centre, for whichever hand did the work."""
    p = data_provider.create_vrs_data_provider(str(vrs))
    hid = p.get_stream_id_from_label("handtracking")
    rgb = p.get_stream_id_from_label("camera-rgb")
    # Everything in this project is timed from the first colour frame, so hand poses get
    # shifted onto that origin here rather than being left on their own clock.
    first = p.get_image_data_by_index(rgb, 0)[1].capture_timestamp_ns

    found = {}
    for side in ("left", "right"):
        ts, sp, cen = [], [], []
        for i in range(p.get_num_data(hid)):
            s = p.get_hand_pose_data_by_index(hid, i)
            h = s.left_hand if side == "left" else s.right_hand
            if h is None:
                continue
            lm = np.asarray(h.landmark_positions_device).reshape(-1, 3)
            if len(lm) < 21:
                continue
            ts.append((s.tracking_timestamp.total_seconds() * 1e9 - first) / 1e9)
            sp.append(np.linalg.norm(lm - lm.mean(axis=0), axis=1).mean() * 100)
            cen.append(lm.mean(axis=0))
        if len(ts) > 10:
            found[side] = (np.array(ts), np.array(sp), np.array(cen))
    if not found:
        return None
    # The acting hand is the one that travelled furthest. A recording can track the idle
    # hand perfectly and tell us nothing, which is how notebook 1 once analysed a hand
    # that spent the whole recording resting on the table.
    side = max(found, key=lambda s: np.linalg.norm(np.diff(found[s][2], axis=0), axis=1).sum())
    ts, sp, _ = found[side]
    k = SMOOTH
    sm = np.convolve(sp, np.ones(k) / k, mode="same")
    # A moving average has nothing to average at the two ends, so those samples come back
    # pulled towards zero. We hold the first and last good values instead.
    sm[:k] = sm[k]
    sm[-k:] = sm[-k - 1]
    return side, ts, sp, sm


def two_levels(sm, bins=64):
    """The cut that best splits the signal in two, with the mean of each side."""
    h, edges = np.histogram(sm, bins=bins)
    mids = (edges[:-1] + edges[1:]) / 2
    w = h / h.sum()
    best, cut = -1.0, float(np.median(sm))
    for i in range(1, bins):
        w0, w1 = w[:i].sum(), w[i:].sum()
        if w0 == 0 or w1 == 0:
            continue
        m0 = (w[:i] * mids[:i]).sum() / w0
        m1 = (w[i:] * mids[i:]).sum() / w1
        # Otsu's criterion. The best cut is the one that puts the most variance between
        # the two groups, which for a signal that really does sit at two levels lands in
        # the empty space between them.
        between = w0 * w1 * (m0 - m1) ** 2
        if between > best:
            best, cut = between, mids[i]
    return float(cut), float(sm[sm < cut].mean()), float(sm[sm >= cut].mean())


def intervals(ts, sm, cut, gap):
    """Stretches where the hand is closed, with hysteresis so it cannot chatter at the cut."""
    # Two thresholds rather than one. A single line would have the state flipping back and
    # forth on every wobble while the signal sits near it, chopping one grasp into a dozen.
    enter = cut - 0.1 * gap
    leave = cut + 0.1 * gap
    held, out, start = False, [], None
    for t, v in zip(ts, sm):
        if not held and v < enter:
            held, start = True, t
        elif held and v > leave:
            held = False
            if t - start >= MIN_HOLD_S:
                out.append((start, t))
    if held and ts[-1] - start >= MIN_HOLD_S:
        out.append((start, ts[-1]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*")
    a = ap.parse_args()

    chosen = {r["recording"]: float(r["start_s"]) for r in csv.DictReader(RUNS.open())}
    names = a.only or list(chosen)

    rows, panels = [], []
    for name in names:
        vrs = sorted(RECORDINGS.glob(f"{name}_*.vrs"))
        if not vrs:
            print(f"{name}: no recording, skipped")
            continue
        got = spread_series(vrs[0])
        if got is None:
            print(f"{name}: no hand tracked, skipped")
            continue
        side, ts, sp, sm = got
        cut, lo, hi = two_levels(sm)
        gap = hi - lo
        ok = gap >= MIN_GAP_CM
        ivs = intervals(ts, sm, cut, gap) if ok else []
        # The longest stretch is the demonstration. The short ones are a hand closing to
        # move something out of the way or passing through a posture on the way past.
        best = max(ivs, key=lambda iv: iv[1] - iv[0]) if ivs else None

        t0 = chosen.get(name)
        covered = ""
        if best and t0 is not None:
            # How much of the window we picked by eye falls inside the detected grasp ?
            # That window is the only ground truth available and it was chosen for every
            # recording before any of this was built, so it owes nothing to the method.
            # A fraction says more here than a yes or no, since a detection that misses by
            # a tenth of a second is not the same kind of thing as one that misses outright.
            overlap = max(0.0, min(best[1], t0 + 4.0) - max(best[0], t0))
            covered = f"{overlap / 4.0:.0%}"

        rows.append(dict(recording=name, hand=side, low_cm=round(lo, 2), high_cm=round(hi, 2),
                         gap_cm=round(gap, 2), separable="yes" if ok else "no",
                         n_intervals=len(ivs),
                         held_from_s=round(best[0], 2) if best else "",
                         held_to_s=round(best[1], 2) if best else "",
                         held_s=round(best[1] - best[0], 2) if best else "",
                         covers_chosen_window=covered))
        panels.append((name, side, ts, sp, sm, cut, gap, ivs, t0, ok))
        print(f"{name:<10} {side:<5} levels {lo:.2f} and {hi:.2f} cm, gap {gap:.2f}  "
              + (f"held {best[0]:5.2f} to {best[1]:5.2f} s ({best[1]-best[0]:4.1f} s), "
                 f"covers {covered} of the window chosen by eye" if best
                 else "levels too close to call, no intervals reported"))

    if not rows:
        raise SystemExit("nothing to report")

    with (OUT / "grasp_intervals.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # Six across rather than three, because a figure twice as tall as it is wide cannot be
    # read on a slide or a page. This shape fills the width instead of the height.
    cols = 6 if len(panels) > 6 else len(panels)
    nrows = (len(panels) + cols - 1) // cols
    fig, axes = plt.subplots(nrows, cols, figsize=(3.3 * cols, 2.7 * nrows), sharey=True)
    for ax, (name, side, ts, sp, sm, cut, gap, ivs, t0, ok) in zip(np.atleast_1d(axes).ravel(), panels):
        ax.plot(ts, sp, lw=0.6, color="#CCCCCC")
        ax.plot(ts, sm, lw=1.6, color="#065A82")
        ax.axhline(cut, color="#B85042", ls="--", lw=1)
        for s, e in ivs:
            ax.axvspan(s, e, color="#2C5F2D", alpha=0.18)
        if t0 is not None:
            # The window chosen by eye, drawn as two lines so it cannot be confused with
            # the detected stretch behind it.
            ax.axvline(t0, color="#36454F", lw=1.2)
            ax.axvline(t0 + 4.0, color="#36454F", lw=1.2)
        ax.set_title(f"{name} ({side}) gap {gap:.2f} cm" + ("" if ok else ", too close to call"),
                     fontsize=10)
        ax.grid(alpha=0.25)
    for ax in np.atleast_1d(axes).ravel()[len(panels):]:
        ax.axis("off")
    for ax in np.atleast_2d(axes)[:, 0]:
        ax.set_ylabel("hand spread (cm)")
    for ax in np.atleast_2d(axes)[-1, :]:
        ax.set_xlabel("time (s)")
    fig.suptitle("Spread of the 21 hand landmarks about their own centre.\n"
                 "Shaded green is where the hand reads as closed. The two upright lines are "
                 "the window chosen by eye.", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "grasp_intervals.png", dpi=140)
    print(f"\nwrote {(OUT / 'grasp_intervals.csv').relative_to(REPO)} and "
          f"{(OUT / 'grasp_intervals.png').relative_to(REPO)}")


if __name__ == "__main__":
    main()
