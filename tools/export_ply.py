#!/usr/bin/env python3
"""Rebuild the PLY point clouds from the committed npz files.

Why these are not in git. The npz already holds every point, kept frame by frame and the
PLY is the same points with the frames concatenated into one list. Carrying both means
storing the same 36 MB twice and since every re-run of the pipeline rewrites them, git
would keep a fresh full copy of both each time.

The PNG renders are committed by contrast, because they are a tenth of the size and they
can be read on GitHub without downloading anything. A PLY has to be downloaded and opened
in CloudCompare or MeshLab either way, so a command that takes a second costs nothing.

    python3 tools/export_ply.py
    python3 tools/export_ply.py scoop_01 pour_02

It runs on a fresh clone with no recordings, because the npz files are committed.
"""

import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "outputs"


def write_ply(path, pts):
    """Plain ASCII PLY. No colours and no faces, since these are loose points."""
    with path.open("w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(pts)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("end_header\n")
        for x, y, z in pts:
            f.write(f"{x:.5f} {y:.5f} {z:.5f}\n")


def main():
    only = set(sys.argv[1:])
    files = sorted(OUT.glob("object_*_clouds.npz"))
    if not files:
        raise SystemExit("no cloud files in outputs/")

    n = 0
    for npz in files:
        name = re.sub(r"^object_|_clouds\.npz$", "", npz.name)
        if only and name not in only:
            continue
        z = np.load(npz)
        # The per frame arrays are already in room coordinates, so stacking them is the
        # whole conversion. The frame each point came from is what gets lost here, which
        # is why the npz stays the file to work from.
        pts = np.vstack([z[k] for k in sorted(z.files) if k.startswith("frame_")])
        out = OUT / f"object_{name}_cloud_world.ply"
        write_ply(out, pts)
        print(f"{out.name}: {len(pts):,} points")
        n += 1
    if only and not n:
        raise SystemExit(f"no cloud files matching: {', '.join(sorted(only))}")
    print(f"\nwrote {n} file{'s' if n != 1 else ''}")


if __name__ == "__main__":
    main()
