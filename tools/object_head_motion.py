#!/usr/bin/env python3
"""Measure how far the glasses themselves moved during each object pipeline window.

Any object figure measured against the glasses has to be read alongside this. The hand
and the head belong to the same person, so the head follows the hand and the difference
between them stays small and fairly consistent. An object on a table owes the head
nothing. Turn your head a lot while the object barely moves and the glasses record a large
movement for a stationary object, so converting to room coordinates shrinks that movement
rather than growing it.

That is why the object's room-to-glasses ratio is not a stable number while the wrist's
is. Head travel per window is what explains the difference.

    python3 tools/object_head_motion.py

It needs the recordings, so it does not run on a fresh clone. Its output is committed and
`tools/object_summary.py` picks it up if it is there.
"""

import csv
import re
from pathlib import Path

import numpy as np

from projectaria_tools.core import data_provider
from projectaria_tools.core.sensor_data import VioStatus, TrackingQuality

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "outputs"
RECORDINGS = REPO / "recordings"


def vrs_for(name):
    """Which recording a result came from.

    Output names mostly match their recording. One recording can hold a second object
    though, named for eg. scoop_01_bowl, so when the full name finds nothing we drop the
    trailing part and look again.
    """
    hits = sorted(RECORDINGS.glob(f"{name}_*.vrs"))
    if not hits and "_" in name:
        hits = sorted(RECORDINGS.glob(f"{name.rsplit('_', 1)[0]}_*.vrs"))
    return hits[0] if hits else None


def head_motion(vrs, t_from, t_to):
    """Net and total travel of the device origin in the room frame, over one window."""
    provider = data_provider.create_vrs_data_provider(str(vrs))
    rgb_id = provider.get_stream_id_from_label("camera-rgb")
    vio_id = provider.get_stream_id_from_label("vio")
    # Every time in the pipeline is measured from the first colour frame, so we have to
    # start from the same place or the window would sit somewhere else entirely.
    first_ns = provider.get_image_data_by_index(rgb_id, 0)[1].capture_timestamp_ns

    ts, ps = [], []
    for i in range(provider.get_num_data(vio_id)):
        v = provider.get_vio_data_by_index(vio_id, i)
        # The same two quality flags the pipeline uses, so we are measuring the head over
        # the poses the object positions were actually built from.
        if v.status != VioStatus.VALID or v.pose_quality != TrackingQuality.GOOD:
            continue
        t = (v.capture_timestamp_ns - first_ns) / 1e9
        if t < t_from or t > t_to:
            continue
        M = np.asarray((v.transform_odometry_bodyimu @ v.transform_bodyimu_device)
                       .to_matrix()).reshape(4, 4)
        ts.append(t)
        ps.append(M[:3, 3])
    if len(ps) < 2:
        return None
    p = np.stack(ps)
    return dict(
        poses=len(p),
        head_net_cm=float(np.linalg.norm(p[-1] - p[0]) * 100),
        head_path_cm=float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum() * 100),
    )


def main():
    rows = []
    for traj in sorted(OUT.glob("object_*_trajectory.csv")):
        name = re.sub(r"^object_|_trajectory\.csv$", "", traj.name)
        vrs = vrs_for(name)
        if vrs is None:
            print(f"{name}: no recording, skipped")
            continue
        times = [float(r["time_s"]) for r in csv.DictReader(traj.open())]
        m = head_motion(vrs, min(times), max(times))
        if m is None:
            print(f"{name}: no usable poses in the window, skipped")
            continue
        rows.append(dict(recording=name, t_from=min(times), t_to=max(times), **m))
        print(f"{name:<12} window {min(times):5.2f} to {max(times):5.2f} s   "
              f"head moved {m['head_net_cm']:5.1f} cm net, {m['head_path_cm']:6.1f} cm travelled")

    if not rows:
        raise SystemExit("nothing to write")
    path = OUT / "object_head_motion.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
