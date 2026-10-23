#!/usr/bin/env python3
"""Search a recording for usable click points and rank them on a contact sheet.

The pipeline needs one click on the object in one frame and a person chooses it. Choosing
by eye is slow, because the object is only briefly a distinct thing. A spoon's scoop
spends most of a recording buried in cereal with only a thin handle showing, which SAM
reads as part of the bowl or part of the arm.

This does the searching with compute. It samples moments when the acting hand is moving,
samples points around the hand in each one, runs SAM on every combination and ranks what
comes back. You look at one contact sheet and pick.

    python3 tools/find_prompt.py scoop_03
    python3 tools/find_prompt.py pour_01 --from 2 --to 20 --expect 8000 40000

It makes no decision. It narrows a few hundred possibilities to a dozen worth looking at,
which is the part a person is good at.

**A panel here is a candidate. It is not an answer.** This runs SAM on a single frame
while the pipeline runs SAM 2 over the video, carrying a memory between frames and the
two do not always choose the same object from the same point. A click giving a clean
spoon sized mask here can give the whole bowl once the video tracker has it. Run the
pipeline, then check the frames with `tools/check_tracking.py` before believing anything.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from projectaria_tools.core import data_provider
from projectaria_tools.core.sensor_data import (
    TimeDomain, TimeQueryOptions, VioStatus, TrackingQuality)


# A held object sits in this band for our recordings. The spoon lands near 5,000 and the
# larger props higher, so the default is wide and the flag narrows it per object.
DEFAULT_EXPECT = (2500, 12000)


def acting_hand(provider):
    """Whichever hand travelled furthest, which is the one holding the object."""
    sid = provider.get_stream_id_from_label("handtracking")
    travel = {}
    for side in ("left", "right"):
        pts = []
        for i in range(provider.get_num_data(sid)):
            s = provider.get_hand_pose_data_by_index(sid, i)
            h = s.left_hand if side == "left" else s.right_hand
            if h is not None:
                pts.append(np.asarray(h.get_wrist_position_device()).reshape(-1)[:3])
        if pts:
            a = np.array(pts)
            travel[side] = np.linalg.norm(np.diff(a, axis=0), axis=1).sum()
    return max(travel, key=travel.get) if travel else None


def moving_moments(provider, side, t_from, t_to, n, hold=0.4):
    """Times where the hand has been moving steadily, which is where carrying happens.

    Why speed at all ? An object resting in a bowl gives nothing to click that a later
    frame would not give better. The moment it is clear of everything else is the moment
    it is being carried.

    Why sustained speed ? Peak speed would be the obvious choice. The tracker is given one frame
    and has to recognise the object in the next. Starting at the instant a movement begins
    means the object is about to be lifted, turned and reloaded, so what the tracker sees
    next looks nothing like what it was given. That is exactly how the first attempt at
    scoop_03 failed: a clean 6,269 pixel mask on a spoon lying in a bowl, which the
    tracker then lost within fifty frames as the spoon was picked up.

    So each moment is scored by the slowest the hand gets across a window around it. A
    moment in the middle of a carry scores well. A moment at the start of one does not.
    """
    hid = provider.get_stream_id_from_label("handtracking")
    rgb = provider.get_stream_id_from_label("camera-rgb")
    t0 = provider.get_first_time_ns(rgb, TimeDomain.DEVICE_TIME)

    ts, pos = [], []
    for i in range(provider.get_num_data(hid)):
        s = provider.get_hand_pose_data_by_index(hid, i)
        h = s.left_hand if side == "left" else s.right_hand
        if h is None:
            continue
        ts.append(s.tracking_timestamp.total_seconds() * 1e9)
        pos.append(np.asarray(h.get_wrist_position_device()).reshape(-1)[:3])
    ts, pos = np.array(ts), np.array(pos)
    rel = (ts - t0) / 1e9

    dt = np.diff(ts) / 1e9
    speed = np.linalg.norm(np.diff(pos, axis=0), axis=1) / np.maximum(dt, 1e-6)
    mid = rel[1:]

    keep = (mid >= t_from) & (mid <= t_to)
    mid, speed = mid[keep], speed[keep]
    if len(mid) == 0:
        return []

    # The slowest the hand gets over a window centred on each moment. The minimum is
    # deliberate. It rejects a moment that merely sits next to a burst of movement, keeping
    # only moments that are inside one. A mean would let both through.
    sustained = np.empty_like(speed)
    for i, m in enumerate(mid):
        w = (mid >= m - hold) & (mid <= m + hold)
        sustained[i] = speed[w].min() if w.any() else 0.0

    # Spread the picks out in time so we do not get six frames from one burst.
    order = np.argsort(sustained)[::-1]
    chosen = []
    for i in order:
        if all(abs(mid[i] - c) > 0.8 for c in chosen):
            chosen.append(float(mid[i]))
        if len(chosen) == n:
            break
    return sorted(chosen)


def hand_pixels(provider, side, t_ns):
    """The hand's 21 landmarks projected into the colour image."""
    hid = provider.get_stream_id_from_label("handtracking")
    cal = provider.get_device_calibration()
    rgb_c = cal.get_camera_calib("camera-rgb")
    T = rgb_c.get_transform_device_camera()
    R = np.asarray(T.rotation().to_matrix())
    t = np.asarray(T.translation()).reshape(-1)

    h = provider.get_interpolated_hand_pose_data(hid, t_ns, TimeDomain.DEVICE_TIME)
    if h is None:
        return None, None
    sd = h.left_hand if side == "left" else h.right_hand
    if sd is None:
        return None, None

    lm = np.asarray(sd.landmark_positions_device).reshape(-1, 3)
    px = []
    for q in (lm - t) @ R:
        if q[2] <= 0:
            continue
        p = rgb_c.project(q)
        if p is not None:
            px.append([float(p[0]), float(p[1])])
    if not px:
        return None, None
    # The wrist is landmark 5 and the palm is 20, which was verified on two recordings.
    wrist = (lm[5] - t) @ R
    wp = rgb_c.project(wrist) if wrist[2] > 0 else None
    return np.array(px), (np.array([float(wp[0]), float(wp[1])]) if wp is not None else None)


def candidate_points(px, wrist_px, w, h, step=45, reach=170):
    """A grid of points over the hand and just beyond it, where a held object sits.

    We extend the grid away from the wrist, because you hold a tool by one end and the
    working end carries on past your fingers.
    """
    lo, hi = px.min(axis=0), px.max(axis=0)
    if wrist_px is not None:
        centre = px.mean(axis=0)
        d = centre - wrist_px
        n = np.linalg.norm(d)
        if n > 1:
            # Push the box outward along the hand's own direction.
            lo = np.minimum(lo, lo + d / n * reach)
            hi = np.maximum(hi, hi + d / n * reach)
    xs = np.arange(lo[0], hi[0] + 1, step)
    ys = np.arange(lo[1], hi[1] + 1, step)
    pts = [(int(x), int(y)) for y in ys for x in xs
           if 5 <= x < w - 5 and 5 <= y < h - 5]
    return pts


def score(mask, pt, w, h, expect):
    """Rank a mask. Lower is better. None means reject it outright."""
    n = int(mask.sum())
    if n < expect[0] or n > expect[1]:
        return None
    ys, xs = np.nonzero(mask)
    # Anything running off the frame edge is the table, the arm or the background.
    if xs.min() <= 2 or ys.min() <= 2 or xs.max() >= w - 3 or ys.max() >= h - 3:
        return None
    bw, bh = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    fill = n / float(bw * bh)
    # A held object fills a decent part of its own box. A sprawling region does not.
    if fill < 0.18:
        return None
    # Prefer masks sitting near the middle of the expected size band.
    target = (expect[0] + expect[1]) / 2.0
    return abs(np.log(n / target)) + 0.5 * (1.0 - fill)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording")
    ap.add_argument("--from", dest="t_from", type=float, default=1.0)
    ap.add_argument("--to", dest="t_to", type=float, default=None)
    ap.add_argument("--moments", type=int, default=7, help="how many moments to try")
    ap.add_argument("--expect", type=int, nargs=2, default=list(DEFAULT_EXPECT),
                    metavar=("MIN", "MAX"), help="plausible mask size in pixels")
    ap.add_argument("--out", default=None, help="where to write the contact sheet")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parent.parent
    found = sorted((repo / "recordings").glob(f"{args.recording}_*.vrs"))
    if not found:
        print(f"no recording matching {args.recording}", file=sys.stderr)
        return 1

    from ultralytics import SAM
    provider = data_provider.create_vrs_data_provider(str(found[0]))
    rgb = provider.get_stream_id_from_label("camera-rgb")
    t0 = provider.get_first_time_ns(rgb, TimeDomain.DEVICE_TIME)
    t1 = provider.get_last_time_ns(rgb, TimeDomain.DEVICE_TIME)
    dur = (t1 - t0) / 1e9
    t_to = args.t_to if args.t_to is not None else dur - 1.0

    side = acting_hand(provider)
    print(f"{found[0].name}, {dur:.1f} s, acting hand is the {side}")

    moments = moving_moments(provider, side, args.t_from, t_to, args.moments)
    print(f"trying {len(moments)} moments: " + ", ".join(f"{m:.1f}" for m in moments))

    sam = SAM(str(repo / "models" / "sam2_b.pt"))
    results, tried = [], 0
    for t_s in moments:
        t_ns = t0 + int(t_s * 1e9)
        img = provider.get_image_data_by_time_ns(
            rgb, t_ns, TimeDomain.DEVICE_TIME, TimeQueryOptions.CLOSEST)[0].to_numpy_array()
        h, w = img.shape[:2]
        px, wrist_px = hand_pixels(provider, side, t_ns)
        if px is None:
            continue
        for (u, v) in candidate_points(px, wrist_px, w, h):
            tried += 1
            r = sam(img, points=[[u, v]], labels=[1], verbose=False)[0]
            if r.masks is None or len(r.masks) == 0:
                continue
            m = r.masks.data[0].cpu().numpy() > 0.5
            sc = score(m, (u, v), w, h, args.expect)
            if sc is not None:
                results.append((sc, t_s, u, v, int(m.sum()), img, m))

    print(f"tried {tried} points, {len(results)} plausible")
    if not results:
        print("nothing in range. Widen --expect or change the time window.")
        return 1

    # Drop near duplicates, since neighbouring grid points often give the same mask.
    results.sort(key=lambda r: r[0])
    kept = []
    for r in results:
        if all(not (abs(r[1] - k[1]) < 0.3 and abs(r[4] - k[4]) / max(k[4], 1) < 0.15)
               for k in kept):
            kept.append(r)
        if len(kept) == 12:
            break

    print(f"\n{'rank':>4} {'t':>6} {'point':>14} {'pixels':>9}")
    for i, (sc, t_s, u, v, n, _, _) in enumerate(kept, 1):
        print(f"{i:>4} {t_s:6.2f} {f'({u}, {v})':>14} {n:9,}")

    out = Path(args.out) if args.out else repo / "cache" / f"prompt_{args.recording}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = 4
    rows = (len(kept) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(5.5 * cols, 4 * rows), squeeze=False)
    for ax in axes.flat:
        ax.axis("off")
    for ax, (sc, t_s, u, v, n, img, m) in zip(axes.flat, kept):
        ys, xs = np.nonzero(m)
        cx, cy = int(xs.mean()), int(ys.mean())
        x0, x1 = max(0, cx - 240), min(img.shape[1], cx + 240)
        y0, y1 = max(0, cy - 180), min(img.shape[0], cy + 180)
        ax.imshow(img[y0:y1, x0:x1], extent=[x0, x1, y1, y0])
        ax.contour(np.arange(x0, x1), np.arange(y0, y1), m[y0:y1, x0:x1],
                   levels=[0.5], colors="lime", linewidths=2)
        ax.plot(u, v, "x", color="red", markersize=12, markeredgewidth=2.5)
        ax.set_title(f"t={t_s:.2f}  ({u}, {v})  {n:,} px", fontsize=11)
        ax.axis("on"); ax.set_xticks([]); ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(out, dpi=70, bbox_inches="tight")
    print(f"\ncontact sheet: {out}")
    print("Pick one, then set RECORDING, START_S and PROMPT in object_pipeline.ipynb.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
