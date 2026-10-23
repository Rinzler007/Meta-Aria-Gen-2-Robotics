#!/usr/bin/env python3
"""Run the object pipeline over every recording listed in tools/object_runs.csv.

The notebook is the place to read the pipeline and to work on one recording at a time,
because you can see each step's output next to the code that produced it. It is a poor
place to produce twelve results, since you would be editing the same three lines twelve
times and the notebook would end up holding whichever recording you happened to run last.

So the choices live in a file instead. Each row of `tools/object_runs.csv` names a
recording, the second it starts from and the pixel to click on, which are the only three
things that differ between runs. Everything else the notebook works out for itself.

    python3 tools/run_all_objects.py              # everything in the file
    python3 tools/run_all_objects.py pour_02      # just these

Masks are cached per recording and window, so a second run skips the slow part and takes
a couple of minutes rather than a quarter of an hour. That is what makes it reasonable to
re-run the whole set after a change to the pipeline, which is the point of having this.
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NB = REPO / "notebooks" / "object_pipeline.ipynb"
RUNS = REPO / "tools" / "object_runs.csv"
JUPYTER = Path.home() / "projectaria_gen2_python_env" / "bin" / "jupyter"

# The lines worth echoing as each run goes by. Everything else the notebook prints is
# either setup or calibration, which does not change between recordings.
REPORT = re.compile(
    r"mask at the prompt|mask size|mask area looks wrong|mask held its size|"
    r"usable stretch|first at frame|frames with a 3D position|points per frame|"
    r"frame span|accumulated cloud")


def configure(recording, label, start_s, px, py, duration):
    """Rewrite the three configuration lines in the notebook, leaving its comments alone."""
    d = json.loads(NB.read_text())
    hits = 0
    for c in d["cells"]:
        if c["cell_type"] != "code":
            continue
        s = "".join(c["source"])
        # We want the one cell that defines all three together, so a mention of RECORDING
        # anywhere else in the notebook cannot be edited by accident.
        if not ("RECORDING" in s and "START_S" in s and "PROMPT" in s):
            continue
        s = re.sub(r'RECORDING\s*=\s*"[^"]*"', f'RECORDING  = "{recording}"', s)
        s = re.sub(r'LABEL\s*=\s*"[^"]*"', f'LABEL      = "{label}"', s)
        s = re.sub(r"START_S\s*=\s*[0-9.]+", f"START_S    = {start_s}", s)
        s = re.sub(r"DURATION_S = [0-9.]+", f"DURATION_S = {duration}", s)
        s = re.sub(r"PROMPT\s*=\s*\[[^\]]*\]", f"PROMPT = [{px}, {py}]", s)
        c["source"] = s.splitlines(keepends=True)
        hits += 1
    # If the configuration cell is ever split in two, this would otherwise run the
    # previous recording again and overwrite the wrong outputs without saying anything.
    if hits != 1:
        sys.exit(f"expected one configuration cell in the notebook, found {hits}")
    NB.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")


def run_one(row):
    # A row without a label names its outputs after the recording, which is what every
    # row did before a second object per recording became possible.
    label = row.get("label") or row["recording"]
    # A row without a duration keeps the four seconds every row used before windows
    # could be chosen automatically.
    duration = row.get("duration_s") or "4.0"
    configure(row["recording"], label, row["start_s"], row["prompt_x"], row["prompt_y"], duration)
    print(f"\n=== {label}  start {row['start_s']} s  for {duration} s  "
          f"prompt [{row['prompt_x']}, {row['prompt_y']}] ===", flush=True)
    t0 = time.time()
    # Executing in place means the committed notebook carries the outputs of a real run,
    # which is how the rest of this repository records what was observed.
    r = subprocess.run([
        str(JUPYTER), "nbconvert", "--to", "notebook", "--execute", "--inplace",
        "--ExecutePreprocessor.timeout=3600", str(NB),
    ], cwd=NB.parent, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        print(f"=== {label} FAILED after {time.time() - t0:.0f} s ===", flush=True)
        return False

    # We read the numbers back out of the executed notebook rather than reprinting
    # anything we were carrying, so what appears here is what the run actually produced.
    d = json.loads(NB.read_text())
    for c in d["cells"]:
        for o in c.get("outputs", []):
            for line in "".join(o.get("text", [])).splitlines():
                if REPORT.search(line):
                    print(f"  {line}", flush=True)
    print(f"=== {label} done in {time.time() - t0:.0f} s ===", flush=True)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*", help="recordings to run; default is all of them")
    a = ap.parse_args()

    rows = list(csv.DictReader(RUNS.open()))
    if a.only:
        rows = [r for r in rows if (r.get("label") or r["recording"]) in a.only]
        missing = set(a.only) - {(r.get("label") or r["recording"]) for r in rows}
        if missing:
            sys.exit(f"not in {RUNS.name}: {', '.join(sorted(missing))}")
    if not rows:
        sys.exit("nothing to run")

    failed = [(r.get("label") or r["recording"]) for r in rows if not run_one(r)]
    print(f"\nran {len(rows) - len(failed)} of {len(rows)}")
    if failed:
        print(f"failed: {', '.join(failed)}")
        return 1
    print("now run tools/object_head_motion.py and tools/object_summary.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
