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
comes from VIO, and the wrist pose relative to the glasses comes from the hand tracker, so

    T_room_wrist = T_room_device @ T_device_wrist

is one multiplication of data that is already in the recording.

Why the object's rotation comes from the wrist. While the object is gripped it sits at a
fixed offset X from the wrist, so its motion since the first frame is

    X^-1 @ (T_wrist(0)^-1 @ T_wrist(k)) @ X

Conjugating a rotation by a fixed transform leaves the angle alone, so the object turns by
exactly the same angle as the wrist does even though nobody knows X. That is what makes
this worth reporting rather than guessed at.

The alternative was to recover the rotation from the object's own points, lining each
frame up with the one before and composing the results. That was tried and it does not
work here. Chaining the fits forward through the window and back again should return to
where it started, and instead it finishes 94 to 105 degrees and more than half a metre
away. The fits look good one at a time, with a median residual under 2 mm, while a spoon
or a jug is smooth enough that a fit can slide along its own surface without penalty. Over
a hundred and nineteen frames that becomes a random walk.

    python3 tools/object_pose.py
    python3 tools/object_pose.py pour_01 pour_02

It writes `outputs/object_<recording>_pose.csv` and needs the recordings, since the wrist
poses live in them.

Where the position comes from. The pipeline already puts the object's own points into room
coordinates, so the centre of those points is the object's position and no offset is
needed to get it. The pose written here is that position carrying the wrist's rotation.

How we know the grip held. Expressed in the wrist's own frame, a firmly held object sits
at a fixed offset, so whatever that quantity does across the window measures the
assumption directly. It settles 10 to 20 cm from the wrist and wanders by 1.5 to 5 cm on
eleven of the twelve recordings. The exception is scoop_03 at 15.6 cm, whose window
straddles the moment the spoon is put down, so there the grip genuinely breaks.

The one thing it cannot do is say anything about an object nobody is holding, since there
is no hand to read.
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
        name = r["recording"]
        if a.only and name not in a.only:
            continue
        vrs = sorted(RECORDINGS.glob(f"{name}_*.vrs"))
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
        moved = np.array([np.linalg.norm(T[:3, 3]) for T in rel]) * 100
        flag = "" if (np.isnan(wander) or wander < 8) else "   GRIP SLIPPED, pose unreliable"
        print(f"{name:<10} turned up to {turn.max():5.1f} deg, moved {moved.max():5.1f} cm, "
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
