#!/usr/bin/env python3
"""Decide the hand is holding something by looking at the object, not at the hand.

Why this exists. The first grip detection read the shape of the hand, because the shape of
a hand changes when it closes around something. On our own twelve recordings it agrees 91
per cent of the time. On somebody else's kitchen recording it scores 46.9 per cent, which
is guessing and `tools/grip_features.py` shows the problem is not the particular number we
chose. Every shape we can read off 21 landmarks scores between 50 and 59 per cent there,
and a fit over all twelve of them together reaches 50.5 per cent on frames it was not
fitted on. The shape of a hand does not carry whether the hand holds something.

What carries it instead. Two measurements about the object, both physical.

The first is contact. Holding something means touching it. The pipeline puts the object's
points in room coordinates and the hand tracker gives 21 landmarks per hand, so the
distance from the nearest landmark to the nearest object point says whether the hand
reaches the object at all.

The second was meant to be whether the object travels with the hand, since distance alone
cannot tell holding from touching. While something is gripped it keeps a fixed offset from
the wrist, so we measure where the object sits as seen from the wrist and how much that
wanders over a second. It does not work and the number is reported without being used. Over
one second a hand barely moves, so a hand resting beside a bowl on the table holds just as
fixed an offset as a hand carrying it. Measured over the thirteen windows the wander runs
0.5 to 2.3 cm and the static red bowl reads 0.92 cm while a carried tin reads 0.51 cm, so
the two cases are the wrong way round. It still rises when a grip actually breaks, which is
how `tools/object_pose.py` catches scoop_03 at 15.6 cm over a four second window, so it is
a check on a grip you already believe in and not a way to find one.

Why that should travel better than a hand shape. A distance in centimetres means the same
thing in our lab and in anybody's kitchen. Its threshold is physical: fingers in contact
with a surface are a couple of centimetres from it, plus whatever the measurement is worth.
A flatness threshold is a property of one recording, since it has to be found by splitting
that recording's own values, so it carries nothing from one recording to the next.

    python3 tools/grip_from_object.py                 # every recording with an object cloud
    python3 tools/grip_from_object.py pour_01 grip_02

It writes `outputs/grip_from_object.csv`, one row per recording, with the stretches found
and the distance that separated them.

Where the thresholds come from. The static red bowl in scoop_01 gives this project its
error bar, a median wander of 0.69 cm with a worst frame of 4.62 cm, which is the most an
object position is worth. Hand landmarks carry their own error on top. Both thresholds sit
above that, so a frame that really is a grip is not thrown away by measurement noise. They
are distances in centimetres, which is the whole point. A flatness threshold has to be
found inside the recording it is used on. A centimetre is a centimetre anywhere.

What it cannot do. It needs the object cloud, so it only speaks about an object the
pipeline is already tracking. It answers whether this object is in this hand. It does not
find the objects and in a kitchen where somebody touches a dozen things in a minute,
something has to choose which object to ask about. That is the gap between this and a
detector that works on a recording nobody has set up.

It is also only as good as the reconstruction. Where stereo recovers one end of a spoon and
the hand grips the other, the nearest object point is the length of the spoon away and the
contact test fails on an object that is plainly held. The three scoop windows are that case,
reading 37 to 57 per cent of frames in contact on objects held throughout.

What it does on our own thirteen windows. The six where the object is carried for the whole
window, the three pours and the three picks, come out at 97 to 100 per cent of frames in
contact in a single stretch, which is right. `grip_01` opens with the spoon lying in a bowl
and reads 21.9 per cent, which is right in direction. The static red bowl reads 75.8 per
cent, which is correct for contact and wrong for holding, since the hand works inside that
bowl for the whole window without ever lifting it.

What it does on somebody else's recording. `tools/check_contact_against_pilot.py` runs the
pipeline on half an avocado in Meta's `cook_0` kitchen sequence and scores the result
against their contact labels for that same object. Over 137 frames it agrees 67.2 per cent
of the time and catches 93.8 per cent of the frames they mark, where the hand shape method
scored 46.9 per cent on the same recording. It calls contact on 73.7 per cent of frames
against their 46.7, so it holds on after the avocado is set down and the hand is still
nearby. One window of one recording is not a general result. It is the first time anything
in this project has beaten guessing on data from outside the lab.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from projectaria_tools.core import data_provider
from projectaria_tools.core.sensor_data import VioStatus, TrackingQuality

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "outputs"
RECORDINGS = REPO / "recordings"
RUNS = REPO / "tools" / "object_runs.csv"

# How close the nearest finger has to come to the nearest object point before we call it
# contact. Four centimetres sounds generous for touching something. It is not, once you
# count what goes into the measurement: the object's own position is worth about 0.7 cm at
# the median and 4.6 cm at its worst, the landmark positions carry their own error and the
# nearest object point is only the nearest one stereo managed to reconstruct, which on a
# thin spoon handle can be a centimetre off the real surface.
CONTACT_CM = 4.0

# The signal is sampled per frame and a single frame where a finger strays is not a release.
# A median over this many frames, which is about a third of a second at 30 fps, removes
# those without blunting a real release.
SMOOTH = 9

# Hysteresis. We start calling it held when the distance drops a centimetre below the cut
# and stop when it rises a centimetre above, so a distance sitting exactly on the cut cannot
# flip the answer every frame.
MARGIN_CM = 1.0

# A stretch shorter than this is not somebody picking something up. It is the detection
# flickering and on their kitchen recording the old method produced 85 of them.
MIN_HOLD_S = 0.3

# The stretch of time the wander is measured over. One second is a few arm movements. The
# wander is reported and takes no part in the decision, for the reason given above.
WANDER_S = 1.0


def room_from_device(vrs):
    """Every VIO pose in the recording, as times and 4 by 4 matrices taking device to room.

    We read all of them once and interpolate later by nearest sample, because opening the
    recording and walking its streams is the slow part and the window is small.
    """
    p = data_provider.create_vrs_data_provider(str(vrs))
    vid = p.get_stream_id_from_label("vio")
    rgb = p.get_stream_id_from_label("camera-rgb")
    first = p.get_image_data_by_index(rgb, 0)[1].capture_timestamp_ns
    ts, mats = [], []
    for i in range(p.get_num_data(vid)):
        v = p.get_vio_data_by_index(vid, i)
        # The same two quality flags the pipeline applies everywhere else. One bad pose
        # would throw the hand across the room and invent a release that never happened.
        if v.status != VioStatus.VALID or v.pose_quality != TrackingQuality.GOOD:
            continue
        ts.append((v.capture_timestamp_ns - first) / 1e9)
        mats.append(np.asarray((v.transform_odometry_bodyimu @ v.transform_bodyimu_device)
                               .to_matrix()).reshape(4, 4))
    return p, first, np.array(ts), (np.stack(mats) if mats else np.zeros((0, 4, 4)))


def hand_points_in_room(provider, first_ns, vio_ts, vio_mats):
    """Hand landmarks moved into room coordinates, one entry per hand sample.

    The landmarks come out of the tracker in the device frame, which rides on your head, so
    a landmark that never moves relative to your face sits still in that frame while you
    walk across the room. The object cloud lives in room coordinates, so the hand has to
    come to it before any distance between the two means anything.
    """
    hid = provider.get_stream_id_from_label("handtracking")
    out = []
    for i in range(provider.get_num_data(hid)):
        s = provider.get_hand_pose_data_by_index(hid, i)
        t = (s.tracking_timestamp.total_seconds() * 1e9 - first_ns) / 1e9
        if len(vio_ts) == 0:
            continue
        j = int(np.argmin(np.abs(vio_ts - t)))
        # Further than this from any good VIO pose and we do not know where the head was,
        # so the frame is dropped. Placing it by a stale pose would invent a movement.
        if abs(vio_ts[j] - t) > 0.05:
            continue
        T = vio_mats[j]
        sides = {}
        for side in ("left", "right"):
            hand = s.right_hand if side == "right" else s.left_hand
            if hand is None:
                continue
            lm = np.asarray(hand.landmark_positions_device).reshape(-1, 3)
            if len(lm) != 21:
                continue
            # The rotation turns the landmarks to face the way the room does and the
            # translation carries them to where the head was standing.
            # The wrist pose comes along for the ride, because the second half of the test
            # needs to know where the object sits as seen from the wrist and the same two
            # transforms produce it.
            wrist = T @ np.asarray(hand.transform_device_wrist.to_matrix()).reshape(4, 4)
            sides[side] = (lm @ T[:3, :3].T + T[:3, 3], wrist)
        if sides:
            out.append((t, sides))
    return out


def wrist_frame_offsets(traj_t, centres, hands, side):
    """Where the object sits as seen from the wrist, one row per frame of the object.

    Why from the wrist and not from the room ? Because a gripped object is motionless in
    the wrist's frame by definition. Carry a jug across the kitchen and in room coordinates
    it travels two metres, while seen from the wrist holding it the jug has not moved at
    all. So a reading that stays put here is a grip and a reading that sweeps about is a
    hand moving next to something that stayed where it was.
    """
    hand_t = np.array([h[0] for h in hands])
    out = np.full((len(traj_t), 3), np.nan)
    for k, t in enumerate(traj_t):
        if np.isnan(centres[k]).any() or len(hand_t) == 0:
            continue
        j = int(np.argmin(np.abs(hand_t - t)))
        if abs(hand_t[j] - t) > 0.05 or side not in hands[j][1]:
            continue
        T = hands[j][1][side][1]
        # Going from the room into the wrist frame means undoing the wrist pose. For a
        # rigid transform the inverse is the transpose of the rotation applied to the
        # position with the translation taken off first, which costs nothing to compute
        # and avoids inverting a matrix four hundred times.
        out[k] = T[:3, :3].T @ (centres[k] - T[:3, 3])
    return out


def wander_cm(traj_t, offsets, window_s):
    """How far the object moves in the wrist's frame over a short stretch around each frame.

    The measure is the median distance from the middle reading, which is the same quantity
    `tools/object_pose.py` writes out as grip wander, so a number here can be compared with
    one there. Why the median and not the largest ? Because the object's position comes from
    the centre of whatever points stereo managed to reconstruct that frame and when the
    object turns and one face goes out of view that centre jumps. Taking the largest
    distance made a firmly held jug read 10 cm on the strength of a handful of frames like
    that. The median ignores them and still rises when the grip really goes.
    """
    out = np.full(len(traj_t), np.nan)
    half = window_s / 2
    for k, t in enumerate(traj_t):
        sel = offsets[(traj_t >= t - half) & (traj_t <= t + half)]
        sel = sel[~np.isnan(sel).any(axis=1)]
        if len(sel) < 3:
            continue
        out[k] = float(np.median(np.linalg.norm(sel - np.median(sel, axis=0), axis=1)) * 100)
    return out


def nearest_distances(clouds, traj_t, hands):
    """For every frame of the object, how close the nearer hand came, in centimetres.

    Building a tree over the object's points and asking it for each of 21 landmarks is much
    cheaper than the other way round, since a frame holds hundreds of object points and only
    21 landmarks and we want the single smallest distance either way.
    """
    hand_t = np.array([h[0] for h in hands])
    dist, which = [], []
    for k, t in enumerate(traj_t):
        pts = clouds.get(f"frame_{k:03d}")
        if pts is None or len(pts) == 0 or len(hand_t) == 0:
            dist.append(np.nan); which.append(""); continue
        j = int(np.argmin(np.abs(hand_t - t)))
        if abs(hand_t[j] - t) > 0.05:
            dist.append(np.nan); which.append(""); continue
        tree = cKDTree(pts)
        best, best_side = np.inf, ""
        for side, (lm, _wrist) in hands[j][1].items():
            d = tree.query(lm)[0].min()
            if d < best:
                best, best_side = d, side
        dist.append(best * 100.0)
        which.append(best_side)
    return np.array(dist), which


def smooth_median(x, n):
    """A running median that leaves gaps alone.

    A running mean would let one frame where the object cloud collapsed pull its neighbours
    with it. A median ignores that frame entirely, which is what we want from something
    whose job is to survive the occasional bad frame.
    """
    out = np.full(len(x), np.nan)
    half = n // 2
    for i in range(len(x)):
        w = x[max(0, i - half): i + half + 1]
        w = w[~np.isnan(w)]
        if len(w):
            out[i] = np.median(w)
    return out


def stretches(ts, d):
    """Stretches where the hand was in contact with the object.

    Contact is what this measures and contact is all it claims. A hand reaching into a bowl
    that never leaves the table passes this test, which is correct for contact and wrong for
    holding. Their labels mean contact too, so the two can be compared directly.
    """
    # Entering needs to be clearly inside the threshold and leaving clearly outside it, so
    # a distance hovering on the cut cannot flip the state from frame to frame.
    enter, leave = CONTACT_CM - MARGIN_CM, CONTACT_CM + MARGIN_CM
    held, start, out = False, None, []
    for t, v in zip(ts, d):
        if np.isnan(v):
            continue
        if not held and v < enter:
            held, start = True, t
        elif held and v > leave:
            held = False
            if t - start >= MIN_HOLD_S:
                out.append((start, t))
    if held and ts[-1] - start >= MIN_HOLD_S:
        out.append((start, ts[-1]))
    return out


def run_one(label, recording):
    traj = OUT / f"object_{label}_trajectory.csv"
    clouds_path = OUT / f"object_{label}_clouds.npz"
    if not traj.exists() or not clouds_path.exists():
        return None
    vrs = sorted(RECORDINGS.glob(f"{recording}_*.vrs"))
    if not vrs:
        return None

    rows = list(csv.DictReader(traj.open()))
    traj_t = np.array([float(r["time_s"]) for r in rows])
    centres = np.array([[float(r["world_x"]), float(r["world_y"]), float(r["world_z"])]
                        if r["world_x"] else [np.nan] * 3 for r in rows])
    clouds = np.load(clouds_path)

    provider, first_ns, vio_ts, vio_mats = room_from_device(vrs[0])
    hands = hand_points_in_room(provider, first_ns, vio_ts, vio_mats)
    raw, which = nearest_distances(clouds, traj_t, hands)
    d = smooth_median(raw, SMOOTH)

    # Which hand to measure the offset from. We take whichever one came nearest most often,
    # because asking the far hand how steadily it holds the object is meaningless.
    sides = [w for w, v in zip(which, d) if w and not np.isnan(v) and v < CONTACT_CM]
    hand = max(set(sides), key=sides.count) if sides else "right"

    offsets = wrist_frame_offsets(traj_t, centres, hands, hand)
    wander = wander_cm(traj_t, offsets, WANDER_S)

    held = stretches(traj_t, d)
    covered = sum(b - a for a, b in held)
    span = traj_t[-1] - traj_t[0]
    seen = d[~np.isnan(d)]
    seen_w = wander[~np.isnan(wander)]
    inside = float((seen < CONTACT_CM).mean() * 100) if len(seen) else float("nan")

    return {
        "label": label,
        "frames": len(seen),
        "median_cm": round(float(np.median(seen)), 2) if len(seen) else "",
        "closest_cm": round(float(seen.min()), 2) if len(seen) else "",
        "furthest_cm": round(float(seen.max()), 2) if len(seen) else "",
        "frames_in_contact_pct": round(inside, 1),
        "median_wander_cm": round(float(np.median(seen_w)), 2) if len(seen_w) else "",
        "stretches": len(held),
        "longest_s": round(max((b - a for a, b in held), default=0.0), 2),
        "covered_pct": round(covered / span * 100, 1) if span else "",
        "hand": hand,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("only", nargs="*", help="labels to run; default is all of them")
    args = ap.parse_args()

    runs = list(csv.DictReader(RUNS.open()))
    picked = []
    for r in runs:
        label = r.get("label") or r["recording"]
        if args.only and label not in args.only:
            continue
        picked.append((label, r["recording"]))
    if not picked:
        sys.exit("nothing to run")

    results = []
    for label, recording in picked:
        row = run_one(label, recording)
        if row is None:
            print(f"{label:<16} no object cloud, skipped")
            continue
        results.append(row)
        print(f"{row['label']:<16} nearest {row['median_cm']:>5} cm   "
              f"wander {row['median_wander_cm']:>5} cm   "
              f"in contact {row['frames_in_contact_pct']:>5}% of frames   "
              f"{row['stretches']} stretch(es), longest {row['longest_s']:>5} s   {row['hand']}")

    if not results:
        sys.exit("no recordings had an object cloud")

    dest = OUT / "grip_from_object.csv"
    with open(dest, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)

    one = sum(1 for r in results if r["stretches"] == 1)
    print(f"\n{one} of {len(results)} windows give a single stretch of contact")
    print(f"wrote {dest.relative_to(REPO)}")


if __name__ == "__main__":
    main()
