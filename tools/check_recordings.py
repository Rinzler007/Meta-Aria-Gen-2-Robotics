#!/usr/bin/env python3
"""Check Aria recordings and build the manifest in docs/recordings.md.

Two jobs, because they ask the same questions of the same files.

Run it on a fresh recording while you are still standing in the lab. If something is
wrong you can put the glasses back on and record again, which is impossible once you
have gone home.

    python3 tools/check_recordings.py recordings/scoop_*.vrs

Run it with --manifest to regenerate the inventory of everything in recordings/.

    python3 tools/check_recordings.py --manifest

A note on the thresholds below. Hand tracking and pose quality are judged by *where* the
missing samples sit rather than by what fraction of them pass. A recording can track the
idle hand perfectly and be useless and samples missing before the hand first appears cost
nothing while a gap in the middle breaks the demonstration. Judging by fraction raises
warnings on perfectly good recordings and a tool that cries wolf gets ignored.
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import matplotlib
# We pick a file backend before pyplot loads, because this runs in a terminal where there
# is no window for a figure to appear in.
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from projectaria_tools.core import data_provider
from projectaria_tools.core.sensor_data import (
    TimeDomain, TimeQueryOptions, VioStatus, TrackingQuality)


# The streams the rest of the pipeline reads. A recording missing any of these was made on
# the wrong profile and nothing downstream will work.
REQUIRED = ["camera-rgb", "handtracking", "vio", "vio_high_frequency",
            "eyegaze", "slam-front-left", "slam-front-right"]

# A gap inside the tracked stretch cannot be filled in by interpolation, so a recording
# carrying one has effectively ended there. One second at thirty samples a second.
MAX_INTERNAL_GAP = 30

# VIO needs a moment to work out where it is when a recording starts. Anything rejected
# inside this window is startup rather than failure and the two still seconds we record
# at the top of every clip cover it.
VIO_SETTLE_S = 2.0

# Above this much head travel the wearer was walking rather than working at a bench. A
# bench recording keeps the head inside about 150 cm while walking across a room runs to
# thousands, so the line has plenty of room on both sides.
WALKING_CM = 400.0


def rate_of(provider, label):
    """A stream's real sampling rate, taken from the file index without reading records."""
    sid = provider.get_stream_id_from_label(label)
    if sid is None:
        return None, None, None
    n = provider.get_num_data(sid)
    if n < 2:
        return n, 0.0, 0.0
    t0 = provider.get_first_time_ns(sid, TimeDomain.DEVICE_TIME)
    t1 = provider.get_last_time_ns(sid, TimeDomain.DEVICE_TIME)
    span = (t1 - t0) / 1e9
    return n, span, (n / span if span > 0 else 0.0)


def hand_report(provider):
    """For each hand: how often it was seen, where the misses are and how far it moved.

    The distance matters because it tells the two hands apart by what they were doing. The
    hand holding the object travels a long way while the resting hand barely moves, so a
    recording where only the resting hand was tracked is useless even at 100 percent.
    """
    sid = provider.get_stream_id_from_label("handtracking")
    n = provider.get_num_data(sid)

    seen = {"left": [], "right": []}
    conf = {"left": [], "right": []}
    pos = {"left": [], "right": []}

    for i in range(n):
        s = provider.get_hand_pose_data_by_index(sid, i)
        for label, side in (("left", s.left_hand), ("right", s.right_hand)):
            # A hand out of view produces nothing at all rather than a poor reading.
            if side is None:
                continue
            seen[label].append(i)
            conf[label].append(side.confidence)
            pos[label].append(np.asarray(side.get_wrist_position_device()).reshape(-1)[:3])

    out = {}
    for label in ("left", "right"):
        idx = np.array(seen[label], dtype=int)
        if idx.size == 0:
            out[label] = None
            continue
        p = np.array(pos[label])
        # Missing samples before the first sighting and after the last one are the hand
        # being out of shot at the edges of the clip. Those cost us nothing. Gaps in the
        # middle are the ones that break a demonstration.
        internal = np.diff(idx) - 1
        out[label] = {
            "count": idx.size,
            "total": n,
            "frac": idx.size / n,
            "conf_min": float(np.min(conf[label])),
            "conf_max": float(np.max(conf[label])),
            "first_s": idx.min() / 30.0,
            "last_s": idx.max() / 30.0,
            "worst_internal_gap": int(internal.max()) if internal.size else 0,
            "travelled_cm": float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum() * 100),
            "span_cm": np.ptp(p, axis=0) * 100,
        }
    return out


def vio_report(provider):
    """Pose quality, plus where in the recording the rejected samples actually sit."""
    sid = provider.get_stream_id_from_label("vio")
    if sid is None:
        return None
    n = provider.get_num_data(sid)
    t0 = provider.get_first_time_ns(sid, TimeDomain.DEVICE_TIME)

    good, bad_times, positions = 0, [], []
    for i in range(n):
        v = provider.get_vio_data_by_index(sid, i)
        if v.status != VioStatus.VALID or v.pose_quality != TrackingQuality.GOOD:
            bad_times.append((v.capture_timestamp_ns - t0) / 1e9)
            continue
        good += 1
        M = np.asarray((v.transform_odometry_bodyimu @ v.transform_bodyimu_device)
                       .to_matrix()).reshape(4, 4)
        positions.append(M[:3, 3])

    pos = np.array(positions)
    return {
        "good": good,
        "total": n,
        "bad_after_settle": sum(1 for t in bad_times if t > VIO_SETTLE_S),
        "last_bad_s": max(bad_times) if bad_times else 0.0,
        # How far the glasses themselves travelled, which separates working at a bench
        # from walking across a room.
        "head_travel_cm": float(np.linalg.norm(np.diff(pos, axis=0), axis=1).sum() * 100),
        "head_span_cm": np.ptp(pos, axis=0) * 100,
    }


def contact_sheet(provider, vrs_path):
    """Twelve frames spread across the recording, written next to the file.

    This is the check the numbers cannot do for us. No measurement tells you the task was
    out of shot or that the wearer was looking across the room at the critical moment. A
    glance at twelve frames does.
    """
    sid = provider.get_stream_id_from_label("camera-rgb")
    if sid is None:
        return None
    first = provider.get_first_time_ns(sid, TimeDomain.DEVICE_TIME)
    last = provider.get_last_time_ns(sid, TimeDomain.DEVICE_TIME)

    fig, axes = plt.subplots(3, 4, figsize=(18, 11))
    for ax, t_ns in zip(axes.flat, np.linspace(first, last, 12)):
        d, rec = provider.get_image_data_by_time_ns(
            sid, int(t_ns), TimeDomain.DEVICE_TIME, TimeQueryOptions.CLOSEST)
        ax.imshow(d.to_numpy_array())
        # Seconds from the start, because that is what you type into a notebook later.
        ax.set_title(f"t = {(rec.capture_timestamp_ns - first)/1e9:.1f} s", fontsize=11)
        ax.axis("off")
    fig.suptitle(Path(vrs_path).name, fontsize=13)
    plt.tight_layout()

    out = Path(vrs_path).with_suffix(".contact.png")
    # Save before anything can close the figure or we write a blank white image.
    fig.savefig(out, dpi=90, bbox_inches="tight")
    plt.close(fig)
    return out


def measure(vrs_path):
    """Everything we know how to ask about one recording, in one dictionary."""
    provider = data_provider.create_vrs_data_provider(str(vrs_path))
    present = {provider.get_label_from_stream_id(s) for s in provider.get_all_streams()}
    n_rgb, duration, rgb_hz = rate_of(provider, "camera-rgb")

    hands = hand_report(provider)
    # Whichever hand travelled furthest is the one that did the work.
    acting = None
    if any(hands.values()):
        acting = max((l for l in hands if hands[l]),
                     key=lambda l: hands[l]["travelled_cm"])

    return {
        "path": Path(vrs_path),
        "provider": provider,
        "missing_streams": [s for s in REQUIRED if s not in present],
        "duration_s": duration,
        "rgb_hz": rgb_hz,
        "hands": hands,
        "acting": acting,
        "vio": vio_report(provider),
    }


def verdict(m):
    """Decide pass or fail and say why in words rather than leaving a number to read."""
    problems = []

    if m["missing_streams"]:
        problems.append(f"missing streams: {', '.join(m['missing_streams'])}")

    # Profile 8 would give ten frames a second here and that mismatch is exactly what
    # choosing profile 10 was meant to avoid.
    if m["rgb_hz"] and m["rgb_hz"] < 25:
        problems.append(f"colour video at {m['rgb_hz']:.1f} fps, so not profile 10")

    # The hand doing the work is the only one that has to be tracked well. A recording can
    # sit at 100 percent on the resting hand and still be useless, which is what happened
    # to grip_03.
    a = m["acting"]
    if a is None:
        problems.append("no hand tracked at all")
    else:
        h = m["hands"][a]
        if h["worst_internal_gap"] > MAX_INTERNAL_GAP:
            problems.append(f"{a} hand has a {h['worst_internal_gap']} frame gap mid "
                            f"recording, which is {h['worst_internal_gap']/30:.1f} s")
        other = "left" if a == "right" else "right"
        if m["hands"][other] is None:
            problems.append(f"{other} hand never tracked, check it was meant to be idle")

    v = m["vio"]
    if v is None:
        problems.append("no vio stream")
    elif v["bad_after_settle"] > 0:
        # Rejections inside the settling window are startup. Rejections after it are a
        # tracker that genuinely struggled and that is worth knowing about.
        problems.append(f"{v['bad_after_settle']} poses rejected after the first "
                        f"{VIO_SETTLE_S:.0f} s, so tracking struggled mid recording")

    return problems


def check(paths, sheets=True):
    """Print a full report for each recording and return True when all of them passed."""
    ok_all = True
    for p in paths:
        m = measure(p)
        print("=" * 72)
        print(m["path"].name)
        print("=" * 72)

        print(f"\n  duration {m['duration_s']:.1f} s, colour video {m['rgb_hz']:.1f} fps")
        print(f"  missing streams: {m['missing_streams'] or 'none'}")

        print("\n  hands")
        for label in ("left", "right"):
            h = m["hands"][label]
            if h is None:
                print(f"    {label:5} never detected")
                continue
            role = "ACTING" if label == m["acting"] else "idle"
            print(f"    {label:5} {h['count']:>5}/{h['total']} samples "
                  f"({h['frac']*100:5.1f}%), confidence {h['conf_min']:.3f}-{h['conf_max']:.3f}")
            print(f"          seen from {h['first_s']:.1f} s to {h['last_s']:.1f} s, "
                  f"worst gap inside that {h['worst_internal_gap']} frames")
            print(f"          travelled {h['travelled_cm']:.0f} cm  ->  {role}")

        v = m["vio"]
        if v:
            print(f"\n  pose: {v['good']}/{v['total']} usable, last rejection at "
                  f"t = {v['last_bad_s']:.1f} s")
            moving = "walking" if v["head_travel_cm"] > WALKING_CM else "stationary"
            print(f"  head travelled {v['head_travel_cm']:.0f} cm  ->  {moving}")

        if sheets:
            out = contact_sheet(m["provider"], p)
            if out:
                print(f"\n  contact sheet: {out.name}")
                print("  open it. Is the task in view in every panel ? If not, record again.")

        problems = verdict(m)
        print()
        if problems:
            ok_all = False
            print("  NEEDS ATTENTION")
            for x in problems:
                print(f"    - {x}")
        else:
            print("  LOOKS GOOD")
        print()
    return ok_all


# Recordings we know to be superseded, with the reason. A failed take is evidence rather
# than rubbish, so we keep the file and record why it is not used.
EXCLUDED = {
    "grip_03": "superseded by grip_03b. The device tracked only the idle left hand for "
               "the whole 15 s and never found the right hand holding the spoon, although "
               "the footage looks correct to the eye. A pen grip appears to defeat the "
               "on-device hand tracker, which is a finding worth keeping.",
}


def manifest(repo, dest):
    """Write docs/recordings.md from whatever is actually sitting in recordings/."""
    rec_dir = repo / "recordings"
    files = sorted(rec_dir.glob("*.vrs"))

    lines = [
        "# The recordings",
        "",
        "Generated by `tools/check_recordings.py --manifest`. Re-run it after adding "
        "recordings rather than editing this file by hand.",
        "",
        "The `.vrs` files themselves are far too large for git and are excluded by "
        "`.gitignore`, so this table is the record of what exists and what each one holds.",
        "",
        "The October recordings are also on Drive as mp4s with timestamps burnt in: "
        "[October recordings](https://drive.google.com/drive/folders/1L0lLAV54Fm30vN5Cqwuc7e3UM32n7d_4?usp=sharing). "
        "`tools/export_video.py` rebuilds that set from the `.vrs` files.",
        "",
        "| Recording | Task | Duration | Acting hand | Hand tracking | Pose | Head | Status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    notes = []
    for f in files:
        # The device appends a timestamp like _20261008_150452 to whatever name we gave it
        # at record time. Splitting on that recovers our own name and dropping the suffix
        # covers the older files that carry no timestamp at all.
        stem = f.name.split("_2026")[0]
        if stem.endswith(".vrs"):
            stem = stem[:-4]

        try:
            m = measure(f)
        except Exception as exc:                      # noqa: BLE001
            lines.append(f"| `{f.name}` | ? | ? | ? | ? | ? | ? | could not open: {exc} |")
            continue

        # The task is the name with its take number removed, so scoop_01 and scoop_02 group
        # together. We match the trailing take rather than stripping characters, because
        # stripping would eat real letters off a name that happens to end in one of them.
        m_task = re.match(r"^(.*?)_\d+[a-z]?$", stem)
        task = m_task.group(1) if m_task else stem
        a = m["acting"]
        h = m["hands"][a] if a else None
        v = m["vio"]

        hand_txt = (f"{h['frac']*100:.0f}%, gap {h['worst_internal_gap']}" if h
                    else "none tracked")
        pose_txt = f"{v['good']}/{v['total']}" if v else "none"
        head_txt = (f"{v['head_travel_cm']:.0f} cm "
                    f"{'walking' if v['head_travel_cm'] > WALKING_CM else 'stationary'}"
                    if v else "?")

        if stem in EXCLUDED:
            status = "**excluded**"
            notes.append((stem, EXCLUDED[stem]))
        else:
            problems = verdict(m)
            status = "usable" if not problems else "check: " + "; ".join(problems)

        lines.append(f"| `{f.name}` | {task} | {m['duration_s']:.1f} s | {a or '-'} | "
                     f"{hand_txt} | {pose_txt} | {head_txt} | {status} |")
        print(f"  measured {f.name}")

    if notes:
        lines += ["", "## Excluded recordings", ""]
        for stem, why in notes:
            lines += [f"**`{stem}`** - {why}", ""]

    lines += [
        "",
        "## Reading the columns",
        "",
        "**Acting hand** is whichever hand travelled furthest, which is the one holding "
        "the object. This matters more than the overall percentage, because a recording "
        "can track the resting hand perfectly and still be useless.",
        "",
        "**Hand tracking** gives the fraction of samples where the acting hand was found, "
        "followed by the worst gap *inside* the tracked stretch. Samples missing before "
        "the hand first appears or after it last appears cost us nothing. A gap in the "
        "middle breaks the demonstration.",
        "",
        "**Pose** counts the device poses passing both quality flags. Rejections in the "
        f"first {VIO_SETTLE_S:.0f} seconds are VIO working out where it is, which the "
        "still period at the start of each recording covers.",
        "",
        "**Head** is how far the glasses themselves travelled. It separates working at a "
        "bench from walking across a room and that matters because a wrist path spanning "
        "metres is the wearer walking rather than reaching.",
        "",
    ]

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines))
    print(f"\nwrote {dest}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="recordings to check")
    ap.add_argument("--manifest", action="store_true",
                    help="regenerate docs/recordings.md from everything in recordings/")
    ap.add_argument("--no-sheets", action="store_true",
                    help="skip the contact sheets, which are the slow part")
    args = ap.parse_args()

    # The repository is two levels up from this file, so the script works from anywhere.
    repo = Path(__file__).resolve().parent.parent

    if args.manifest:
        manifest(repo, repo / "docs" / "recordings.md")
        return 0

    if not args.files:
        ap.print_help()
        return 2

    return 0 if check(args.files, sheets=not args.no_sheets) else 1


if __name__ == "__main__":
    sys.exit(main())
