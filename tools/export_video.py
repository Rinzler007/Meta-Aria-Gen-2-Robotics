#!/usr/bin/env python3
"""Export the colour camera of a recording to a shareable mp4.

The `.vrs` files are gigabytes and nobody outside the project can open them, so this makes
something that plays anywhere and can go on a Drive link in the reports and the slides.

    python3 tools/export_video.py                       # every October recording
    python3 tools/export_video.py scoop_01 pour_02      # named ones
    python3 tools/export_video.py --full-res scoop_01   # no downscaling

Files land in `videos/`, which `.gitignore` excludes, because they are derived from the
recordings and would otherwise put hundreds of megabytes into git for no reason.

Every frame carries its timestamp in the corner. That is not decoration. Every result in
this repository is quoted against a time within a recording, for eg. the carry in
`scoop_01` running from 7.2 to 7.8 s and a video without a clock cannot be checked
against any of it.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import cv2

from projectaria_tools.core import data_provider
from projectaria_tools.core.sensor_data import TimeDomain, TimeQueryOptions

# The twelve usable October recordings. grip_03 is left out because the device never
# tracked the hand holding the spoon in it, which `docs/recordings.md` explains.
OCTOBER = ["scoop_01", "scoop_02", "scoop_03",
           "pour_01", "pour_02", "pour_03",
           "pick_01", "pick_02", "pick_03",
           "grip_01", "grip_02", "grip_03b"]

# Half resolution. The colour camera records 2016x1512, which is far more than anyone
# needs to see what the hands were doing and halving it roughly quarters the file.
SCALE = 0.5

# Constant quality rather than constant bitrate, so a still clip costs less than a busy
# one. 23 is the usual sensible default and these come out watchable.
CRF = 23


def annotate(frame, seconds):
    """Burn the timestamp into the top left corner, over a dark strip so it stays legible.

    Why a strip rather than plain text ? Because the table in these recordings is a bright
    orange and white text vanishes against it.
    """
    out = frame.copy()
    label = f"t = {seconds:5.2f} s"
    h, w = out.shape[:2]
    # The box is sized from the text rather than guessed, so it still fits if the font
    # scale changes with resolution.
    scale = max(0.6, w / 1400.0)
    thick = max(1, int(round(scale * 2)))
    (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    pad = int(8 * scale)
    cv2.rectangle(out, (0, 0), (tw + 2 * pad, th + base + 2 * pad), (0, 0, 0), -1)
    cv2.putText(out, label, (pad, th + pad), cv2.FONT_HERSHEY_SIMPLEX,
                scale, (255, 255, 255), thick, cv2.LINE_AA)
    return out


def export(vrs_path, dest, scale=SCALE, crf=CRF):
    """Write one recording's colour stream to an mp4, returning its size in bytes."""
    provider = data_provider.create_vrs_data_provider(str(vrs_path))
    rgb_id = provider.get_stream_id_from_label("camera-rgb")
    n = provider.get_num_data(rgb_id)
    first_ns = provider.get_first_time_ns(rgb_id, TimeDomain.DEVICE_TIME)
    last_ns = provider.get_last_time_ns(rgb_id, TimeDomain.DEVICE_TIME)
    duration = (last_ns - first_ns) / 1e9
    fps = n / duration if duration > 0 else 30.0

    # We take the first frame to learn the size rather than hardcoding one, since a
    # different recording profile would give different dimensions.
    probe = provider.get_image_data_by_index(rgb_id, 0)[0].to_numpy_array()
    h, w = probe.shape[:2]
    ow, oh = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2   # even, H.264 needs it

    # Raw frames go straight into ffmpeg over a pipe. Going through a file would mean
    # writing hundreds of megabytes of intermediate jpegs for nothing.
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{ow}x{oh}", "-r", f"{fps:.4f}",
        "-i", "pipe:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", str(crf),
        # yuv420p is the pixel format that every player and every browser can handle.
        "-pix_fmt", "yuv420p",
        # Lets a player start without downloading the whole file first, which matters on
        # a Drive link.
        "-movflags", "+faststart",
        str(dest),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    for i in range(n):
        data, rec = provider.get_image_data_by_index(rgb_id, i)
        if not data.is_valid():
            continue
        img = data.to_numpy_array()
        if (ow, oh) != (w, h):
            # INTER_AREA is the right choice when shrinking, since it averages rather than
            # sampling and so does not alias the cereal into a shimmering mess.
            img = cv2.resize(img, (ow, oh), interpolation=cv2.INTER_AREA)
        img = annotate(img, (rec.capture_timestamp_ns - first_ns) / 1e9)
        proc.stdin.write(np.ascontiguousarray(img).tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed on {vrs_path.name}")
    return dest.stat().st_size, n, duration, (ow, oh)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="recording names, default is the October set")
    ap.add_argument("--full-res", action="store_true", help="do not halve the resolution")
    ap.add_argument("--crf", type=int, default=CRF, help=f"quality, lower is bigger (default {CRF})")
    args = ap.parse_args()

    # The repository is one level up from tools/, so this works from any directory.
    repo = Path(__file__).resolve().parent.parent
    recordings = repo / "recordings"
    videos = repo / "videos"
    videos.mkdir(exist_ok=True)

    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
        print("ffmpeg not found. brew install ffmpeg", file=sys.stderr)
        return 1

    names = args.names or OCTOBER
    scale = 1.0 if args.full_res else SCALE

    total = 0
    print(f"{'recording':12} {'frames':>7} {'seconds':>8} {'size':>10}  resolution")
    for name in names:
        found = sorted(recordings.glob(f"{name}_*.vrs")) or sorted(recordings.glob(f"{name}.vrs"))
        if not found:
            print(f"{name:12}  not found in {recordings}", file=sys.stderr)
            continue
        dest = videos / f"{name}.mp4"
        size, n, dur, (ow, oh) = export(found[0], dest, scale=scale, crf=args.crf)
        total += size
        print(f"{name:12} {n:>7} {dur:>8.1f} {size/1e6:>8.1f} MB  {ow}x{oh}")

    print(f"\n{len(names)} videos, {total/1e6:.0f} MB total, in {videos}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
