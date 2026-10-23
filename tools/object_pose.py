#!/usr/bin/env python3
"""Pose of the held object in the room, frame by frame, as a 4 by 4 matrix.

The pipeline gives the object's centre in each frame. A centre is three numbers and says
where something is without saying which way up it is. For pouring that is the whole task,
since a jug carried flat and a jug tipped out trace the same path.

A pose is both together:

    T = [ R  t ]      R is a 3 by 3 rotation, how the object is turned
        [ 0  1 ]      t is a 3 by 1 position, where the object is

These compose by multiplying and reverse by inverting, which is what moves a measurement
between frames of reference. The glasses give us two already. Their own pose in the room
comes from VIO. The wrist pose relative to the glasses comes from the hand tracker, so

    T_room_wrist = T_room_device @ T_device_wrist

is one multiplication of data that is already in the recording.

Why the object's rotation comes from the wrist. While the object is gripped it sits at a
fixed offset X from the wrist, so its motion since the first frame is

    X^-1 @ (T_wrist(0)^-1 @ T_wrist(k)) @ X

Conjugating a rotation by a fixed transform leaves the angle alone, so the object turns by
exactly the same angle as the wrist does even though nobody knows X. That is what makes
this worth reporting rather than guessed at.

Why the rotation does not come from the object's own points. Lining each frame up with the
one before it and composing the results does not work on this data. Chaining those fits
forward through a window and back again should return to where it started. It finishes
94 to 105 degrees and more than half a metre away. Each fit looks good alone, with a median
residual under 2 mm, while a spoon or a jug is smooth enough that a fit slides along its own
surface without penalty. Over a hundred frames that becomes a random walk.

    python3 tools/object_pose.py
    python3 tools/object_pose.py pour_01 pour_02

It writes `outputs/object_<recording>_pose.csv` and needs the recordings, since the wrist
poses live in them.

Where the position comes from. The pipeline already puts the object's own points into room
coordinates, so the centre of those points is the object's position and no offset is
needed to get it. The pose written here is that position carrying the wrist's rotation.

Objects that never move are handled separately and need no hand at all. If something stays
put then its pose is one constant matrix. The only useful question is how far the
measurement wanders when the right answer is known to be zero. The red bowl in scoop_01
answers that. Seen from the glasses it appears to travel through a box 13.9 cm across,
purely because the wearer's head moves. Converted into room coordinates that falls to
6.1 cm, with a median wander of 0.69 cm and a worst frame of 4.62 cm. Those are the error
bars for every object position this project reports.

How a held object is told from a resting one. By whether it moves. Anything whose own
motion stays inside the static error gets a constant pose. Anything that exceeds it is treated as
carried and takes the wrist's rotation. The cut sits at STATIC_CM below, drawn
from these recordings, where resting objects measure about 6 cm and carried ones 15 cm and
upwards.

What the grip check does and does not tell you. A held object sits at a fixed offset from
the wrist, so drift in that offset shows the grip breaking, which is how scoop_03 is caught
at 15.6 cm where its window straddles the spoon being put down. A small number does not
prove the object was held. During scoop_01 the hand works inside the red bowl, so the bowl
holds a nearly fixed offset from the wrist too and passes the same test. Use it to reject,
never to confirm.
"""

import argparse
import csv
import re
from pathlib import Path

import numpy as np

from projectaria_tools.core import data_provider
from projectaria_tools.core.sensor_data import VioStatus, TrackingQuality

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "outputs"
RECORDINGS = REPO / "recordings"
RUNS = REPO / "tools" / "object_runs.csv"

WINDOW_S = 4.0

# Below this much movement in the room an object counts as resting. A stationary object
# measured 6.1 cm across its box here, carried ones 15 cm and more, so the line has room on
# both sides. It is drawn from twelve recordings rather than derived, so treat it as a rule
# of thumb and look at the number beside it.
STATIC_CM = 10.0


def turn_degrees(R):
    """How far a rotation turns, whatever axis it turns about."""
    # The trace of a rotation is 1 + 2 cos(theta). The clip is there because rounding can
    # push the argument a hair outside the range arccos accepts.
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1.0, 1.0))))


def turn_axis(R):
    """The axis a rotation turns about, as a unit vector."""
    # The skew symmetric part of a rotation carries its axis. Near zero rotation the axis
    # is meaningless, so we say so rather than return noise.
    v = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([np.nan, np.nan, np.nan])


def wrist_poses(vrs, t_from, t_to, side="right"):
    """The wrist pose in the room for every hand sample inside the window."""
    p = data_provider.create_vrs_data_provider(str(vrs))
    hid = p.get_stream_id_from_label("handtracking")
    vid = p.get_stream_id_from_label("vio")
    rgb = p.get_stream_id_from_label("camera-rgb")
    first = p.get_image_data_by_index(rgb, 0)[1].capture_timestamp_ns

    vt, vM = [], []
    for i in range(p.get_num_data(vid)):
        v = p.get_vio_data_by_index(vid, i)
        # Both quality flags, the same test the rest of the pipeline applies, because one
        # bad pose would swing the object across the room with nothing to catch it.
        if v.status != VioStatus.VALID or v.pose_quality != TrackingQuality.GOOD:
            continue
        vt.append((v.capture_timestamp_ns - first) / 1e9)
        vM.append(np.asarray((v.transform_odometry_bodyimu @ v.transform_bodyimu_device)
                             .to_matrix()).reshape(4, 4))
    if len(vt) < 2:
        return [], []
    vt = np.array(vt)
    vM = np.stack(vM)

    ts, poses = [], []
    for i in range(p.get_num_data(hid)):
        s = p.get_hand_pose_data_by_index(hid, i)
        h = s.right_hand if side == "right" else s.left_hand
        if h is None:
            continue
        t = (s.tracking_timestamp.total_seconds() * 1e9 - first) / 1e9
        if not (t_from <= t <= t_to):
            continue
        Td = np.asarray(h.transform_device_wrist.to_matrix()).reshape(4, 4)
        # Hand samples run at 30 Hz and poses at 10, so each hand sample takes the pose
        # nearest it in time. Matching by index would drift the two apart.
        ts.append(t)
        poses.append(vM[int(np.argmin(np.abs(vt - t)))] @ Td)
    return ts, poses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*")
    a = ap.parse_args()

    runs = list(csv.DictReader(RUNS.open()))
    done = 0
    for r in runs:
        # A row may name its outputs separately from the recording it reads, which is how
        # one recording can carry two objects.
        name = r.get("label") or r["recording"]
        if a.only and name not in a.only:
            continue
        vrs = sorted(RECORDINGS.glob(f"{r['recording']}_*.vrs"))
        if not vrs:
            print(f"{name}: no recording, skipped")
            continue
        t0 = float(r["start_s"])
        ts, poses = wrist_poses(vrs[0], t0, t0 + WINDOW_S)
        if len(poses) < 5:
            print(f"{name}: too few wrist samples in the window, skipped")
            continue

        # The object's position comes from its own points rather than from the hand. The
        # pipeline already wrote those in room coordinates, so this is a lookup.
        traj = OUT / f"object_{name}_trajectory.csv"
        ct, cx = [], []
        if traj.exists():
            for row in csv.DictReader(traj.open()):
                ct.append(float(row["time_s"]))
                cx.append([float(row["world_x"]), float(row["world_y"]), float(row["world_z"])])
        ct, cx = np.array(ct), np.array(cx).reshape(-1, 3)

        obj, offsets = [], []
        for t, Tw in zip(ts, poses):
            T = Tw.copy()
            if len(ct):
                # Hand samples and frames share a clock but not a rate, so each wrist pose
                # takes the frame nearest it in time rather than the one at its own index.
                j = int(np.argmin(np.abs(ct - t)))
                if abs(ct[j] - t) <= 0.05 and not np.isnan(cx[j]).any():
                    T[:3, 3] = cx[j]
                    offsets.append(Tw[:3, :3].T @ (cx[j] - Tw[:3, 3]))
            obj.append(T)

        # How far the object drifts within the hand's own frame. Small means the grip held
        # and the rotation can be carried across to the object. Large means it did not.
        wander = float("nan")
        if len(offsets) >= 10:
            o = np.array(offsets)
            wander = float(np.median(np.linalg.norm(o - np.median(o, axis=0), axis=1)) * 100)

        # Did this object move at all ? A resting one owes nothing to the hand, so it gets
        # one constant pose instead of the wrist's rotation frame by frame.
        span = (np.linalg.norm(cx.max(axis=0) - cx.min(axis=0)) * 100) if len(cx) else float("nan")
        resting = span == span and span < STATIC_CM
        if resting:
            hold = np.eye(4)
            hold[:3, 3] = np.median(cx, axis=0)
            obj = [hold.copy() for _ in obj]

        inv0 = np.linalg.inv(obj[0])
        rel = [inv0 @ T for T in obj]

        dest = OUT / f"object_{name}_pose.csv"
        with dest.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["frame", "time_s", "turned_deg", "axis_x", "axis_y", "axis_z",
                        "grip_wander_cm"]
                       + [f"m{i}{j}" for i in range(3) for j in range(4)])
            for k, (t, T) in enumerate(zip(ts, rel)):
                ax = turn_axis(T[:3, :3])
                w.writerow([k, round(t, 4), round(turn_degrees(T[:3, :3]), 2)]
                           + [("" if np.isnan(v) else round(float(v), 5)) for v in ax]
                           + ["" if np.isnan(wander) else round(wander, 2)]
                           + [round(float(v), 6) for v in T[:3, :4].ravel()])

        turn = np.array([turn_degrees(T[:3, :3]) for T in rel])
        if resting:
            # The scatter of a thing that never moves is the measurement error, so that is
            # what gets reported rather than a rotation it never performed.
            scat = float(np.median(np.linalg.norm(cx - np.median(cx, axis=0), axis=1)) * 100)
            print(f"{name:<14} resting, span {span:5.1f} cm. One fixed pose. "
                  f"Position scatter {scat:4.2f} cm, which is the measurement error")
        else:
            moved = np.array([np.linalg.norm(T[:3, 3]) for T in rel]) * 100
            flag = "" if (np.isnan(wander) or wander < 8) else "   GRIP SLIPPED, pose unreliable"
            print(f"{name:<14} carried, turned up to {turn.max():5.1f} deg, moved {moved.max():5.1f} cm, "
                  f"grip wander {wander:4.1f} cm{flag}")
        done += 1

    if not done:
        raise SystemExit("nothing matched")
    print(f"\nwrote {done} pose files into outputs/")
    print("Each row is the object's pose since the first frame of the window. The position")
    print("comes from the object's own points. The rotation comes from the wrist and equals")
    print("the object's while the grip stays firm. Grip wander is how far the object drifts")
    print("inside the hand's frame, so a large value means that equality has broken.")


if __name__ == "__main__":
    main()
