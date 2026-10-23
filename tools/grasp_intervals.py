#!/usr/bin/env python3
"""Find when a hand takes hold of something and when it lets go.

A recording is one long clip and only part of it is the task. The rest is reaching,
settling and tidying. Bracketing the task automatically is what would let a caregiver
record all day without somebody watching each clip afterwards.

The glasses report 21 landmarks per hand and never say which is which, so any feature
used here has to work without knowing one point from another.

What is measured. The 21 points are reduced to one number per frame: how flat the hand is.
Fit a cloud to the points, take its three principal sizes, and report the smallest against
their total. An open hand is close to a plane and scores near zero. A hand wrapped around
an object is not flat and scores higher. Taking hold of something therefore raises the
number, and letting go lowers it.

Why flatness and not spread. Spread, meaning how far the points sit from their own centre,
was tried first. It works on a spoon and a jug, where the fingers curl tightly, and it
cannot see a tin being picked up at all. Measured across the three tin recordings the hand
reads 4.8 to 5.3 cm of spread while reaching for the tin and 4.4 to 5.3 cm while carrying
it, so there is no gap to find. Flatness separates the same recordings cleanly, moving from
about 0.02 while reaching to about 0.13 while holding.

How well it does. Across the twelve recordings the stretch it marks covers 91 per cent of
the window a person had already picked by eye, and every recording separates into two
levels. Spread managed eight of the twelve and refused the other four.

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
MIN_GAP = 0.04

# An interval shorter than this is not a demonstration of anything. It is the hand passing
# through a posture on its way somewhere else.
MIN_HOLD_S = 0.5


def spread_series(vrs):
    """Flatness of the 21 landmarks per frame, for whichever hand did the work."""
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
            c = lm - lm.mean(axis=0)
            # The three principal sizes of the cloud of landmarks. The smallest against
            # their total says how close the hand is to lying in a plane, which needs no
            # knowledge of which landmark is which.
            ev = np.sort(np.linalg.eigvalsh(c.T @ c / len(c)))
            sp.append(float(ev[0] / ev.sum()))
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


def intervals(ts, sm, cut, gap, held_above=True):
    """Stretches where the hand is closed, with hysteresis so it cannot chatter at the cut."""
    # Two thresholds rather than one. A single line would have the state flipping back and
    # forth on every wobble while the signal sits near it, chopping one grasp into a dozen.
    # Holding raises flatness, so crossing upward starts a hold. The two thresholds sit
    # either side of the cut so the state cannot chatter while the signal hovers on it.
    sign = 1.0 if held_above else -1.0
    enter = sign * (cut + 0.1 * gap)
    leave = sign * (cut - 0.1 * gap)
    held, out, start = False, [], None
    for t, v in zip(ts, sm * sign):
        if not held and v > enter:
            held, start = True, t
        elif held and v < leave:
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
        ok = gap >= MIN_GAP
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

        rows.append(dict(recording=name, hand=side, flat_low=round(lo, 4), flat_high=round(hi, 4),
                         gap=round(gap, 4), separable="yes" if ok else "no",
                         n_intervals=len(ivs),
                         held_from_s=round(best[0], 2) if best else "",
                         held_to_s=round(best[1], 2) if best else "",
                         held_s=round(best[1] - best[0], 2) if best else "",
                         covers_chosen_window=covered))
        panels.append((name, side, ts, sp, sm, cut, gap, ivs, t0, ok))
        print(f"{name:<10} {side:<5} flatness {lo:.3f} to {hi:.3f}, gap {gap:.3f}  "
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
        ax.set_title(f"{name} ({side}) gap {gap:.3f}" + ("" if ok else ", too close to call"),
                     fontsize=10)
        ax.grid(alpha=0.25)
    for ax in np.atleast_1d(axes).ravel()[len(panels):]:
        ax.axis("off")
    for ax in np.atleast_2d(axes)[:, 0]:
        ax.set_ylabel("how flat the hand is")
    for ax in np.atleast_2d(axes)[-1, :]:
        ax.set_xlabel("time (s)")
    fig.suptitle("How flat the hand is, from its 21 landmarks. An open hand is nearly flat "
                 "and a hand wrapped around an object is not.\n"
                 "Shaded green is where the hand reads as holding something. The two upright "
                 "lines are the window chosen by eye.", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "grasp_intervals.png", dpi=140)
    print(f"\nwrote {(OUT / 'grasp_intervals.csv').relative_to(REPO)} and "
          f"{(OUT / 'grasp_intervals.png').relative_to(REPO)}")


if __name__ == "__main__":
    main()
