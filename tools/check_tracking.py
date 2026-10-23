#!/usr/bin/env python3
"""Draw frames from an object pipeline run with the tracked mask outlined over them.

The notebook checks the mask for drift on area alone. Area catches the two loud failures,
a mask collapsing to nothing and a mask swallowing the table and it is blind to the quiet
one. A mask that slides off a spoon and onto a bowl of similar size keeps its area while
tracking the wrong thing entirely and SAM's own confidence stays at 1.00 throughout.

Looking at the frames is the only check for that, so this makes looking cost one command.

    python3 tools/check_tracking.py pour_01
    python3 tools/check_tracking.py pour_01 --frames 0 30 60 119

It reads the cached masks and the exported frames, so it needs a run that has already
happened. It never recomputes anything.
"""

import argparse
import re
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import imageio.v3 as iio

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "cache"


def find_tag(recording):
    """Cache names carry the window, so one recording can have more than one run behind it."""
    hits = sorted(CACHE.glob(f"masks_{recording}_*.npz"))
    if not hits:
        raise SystemExit(f"no cached masks for {recording}. Run the notebook on it first.")
    # The most recent run is the one the committed outputs came from, so that is the one
    # worth looking at when there is a choice.
    newest = max(hits, key=lambda p: p.stat().st_mtime)
    return re.sub(r"^masks_|\.npz$", "", newest.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("recording")
    ap.add_argument("--frames", type=int, nargs="*", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    tag = find_tag(a.recording)
    z = np.load(CACHE / f"masks_{tag}.npz")
    keys = sorted(z.files)
    frames = sorted((CACHE / f"frames_{tag}").glob("*.jpg"))
    if not frames:
        raise SystemExit(f"no exported frames in cache/frames_{tag}")
    H, W = iio.imread(frames[0]).shape[:2]

    # Without a list we spread eight frames over the window, weighted towards the opening
    # frames. A prompt sitting on the wrong object shows itself there first.
    picks = a.frames or [0, 8, 16, 30, 60, 90, 110, len(keys) - 1]
    picks = [p for p in picks if 0 <= p < len(keys)]

    cols = 4
    rows = (len(picks) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3.5 * rows))
    for ax, k in zip(np.atleast_1d(axes).ravel(), picks):
        m = np.unpackbits(z[keys[k]])[:H * W].reshape(H, W).astype(bool)
        ax.imshow(iio.imread(frames[k]))
        ax.contour(m, levels=[0.5], colors="lime", linewidths=1.3)
        ax.set_title(f"frame {k}   {int(m.sum()):,} px", fontsize=9)
        ax.axis("off")
    # Any axes left over from an uneven grid would otherwise show an empty white box.
    for ax in np.atleast_1d(axes).ravel()[len(picks):]:
        ax.axis("off")

    fig.suptitle(tag, fontsize=12)
    fig.tight_layout()
    out = Path(a.out) if a.out else CACHE / f"tracking_{tag}.png"
    fig.savefig(out, dpi=90)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
