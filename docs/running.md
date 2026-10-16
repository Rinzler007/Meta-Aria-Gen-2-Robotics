# Running this repository

The README explains why each thing was built. This file says what to run, in what order,
and what you get back. Start here if you have just cloned the repository.

## The short version

```bash
# once
python3 -m venv ~/projectaria_gen2_python_env
source ~/projectaria_gen2_python_env/bin/activate
pip install -r requirements.txt

# this works on a fresh clone with no data at all
python3 tools/render_object_cloud.py

# everything else needs the recordings
cd notebooks && jupyter notebook
```

## What runs without any data

A fresh clone arrives with the code and the deliverables but none of the recordings, since
they are 5.1 GB and `.gitignore` keeps them out. Two things still work, because what they
read is committed:

| Command                                | What it does                                  | Needs                               |
| -------------------------------------- | --------------------------------------------- | ----------------------------------- |
| `python3 tools/render_object_cloud.py` | Redraws the object cloud figures              | the `object_*_clouds.npz` files     |
| `python3 tools/object_summary.py`      | Collects every run into one table and figure  | the `object_*_trajectory.csv` files |
| `python3 tools/export_ply.py`          | Rebuilds the PLY clouds, which are not in git | the `object_*_clouds.npz` files     |

Everything else needs recordings. You can also read every notebook without running it,
because the cell outputs are committed on purpose. That is the record of what was actually
observed. For most questions reading is faster than rerunning.

## Getting the data

Two routes.

**Record your own.** `docs/glasses_runbook.md` has every command, from pairing through to
download. Use profile 10. Then check what you captured before you leave the lab:

```bash
python3 tools/check_recordings.py recordings/*.vrs
```

That prints stream rates, hand tracking quality, pose quality and a verdict. It also writes
a twelve panel contact sheet next to each file. Look at the sheets. If the task is not in
view in every panel, record again, because that is the one thing you cannot fix later.

**Use the existing recordings.** They are not in git. `docs/recordings.md` lists all of
them with what each contains, so you can see what you are missing. Ask for the files.

## The notebooks, in order

Read the order column rather than the filenames, which carry no numbers. Run them from the
`notebooks` folder so each one can work the repository out from its own location.

| Order | Notebook                           | Needs                                                   | Produces                                                    | Time                                 |
| ----- | ---------------------------------- | ------------------------------------------------------- | ----------------------------------------------------------- | ------------------------------------ |
| 1     | `vrs_basics_hand_trajectory.ipynb` | `scoop_01`                                              | `wrist_speed_segmented_clean.png`                           | 2 min                                |
| 2     | `device_calibration.ipynb`         | `scoop_01`                                              | nothing, it prints and plots                                | 2 min                                |
| 3     | `object_pipeline.ipynb`            | `scoop_01`, SAM weights                                 | the four `object_scoop_01_*` deliverables                   | 15 min cold, 3 min with cached masks |
| 4     | `wrist_world_frame.ipynb`          | the twelve October recordings plus `pouring_scooping_1` | `wrist_world_frame_summary.png` and `.csv`, one path figure | 10 min                               |
| 5     | `activity_segmentation.ipynb`      | the same thirteen                                       | `activity_segmentation.png` and `.csv`                      | 10 min                               |

The times are rough. They were measured on an M1 with no GPU, except the cold run of notebook 3,
which depends on how long SAM 2 takes to propagate on your machine.

### What depends on what

Nothing. The five numbered notebooks are independent of each other and each reads the recordings
directly, so you can run any one of them on its own.

`object_pipeline.ipynb` is the slow one on a first run, because SAM 2 encodes every frame and
carries a memory between them. It caches the masks, so a second run skips that entirely. Set
`FORCE_PROPAGATION` when you change the prompt or the window.

### Redrawing the cloud without recomputing it

```bash
python3 tools/render_object_cloud.py
```

Notebook 3 writes the cloud data and also draws the figure. This script redraws it from the npz
alone, which is the only thing in the repository that runs on a fresh clone with no recordings,
because the npz is committed and the 5.1 GB of recordings are not.

## Pointing the pipeline at a different recording

`object_pipeline.ipynb` holds its whole configuration in one cell:

```python
RECORDING  = "scoop_01"
START_S    = 7.6
DURATION_S = 4.0
PROMPT     = [1090, 820]
MAX_DEPTH  = 2.0
SEARCH_RADIUS = 0.25
```

To run it on `pour_02`, change `RECORDING`, pick a window where the object is moving, then find
a `PROMPT`. Everything else derives from those. Cache names carry the window so two windows
cannot collide, while the deliverables are named per recording so there is one current result
for each.

Notebooks 1, 2, 4 and 5 take a filename near the top and nothing else.

### Where the twelve choices are kept

Those three numbers are the only thing that differs between one run and the next, so they
live in `tools/object_runs.csv`, one row per recording, each with a note saying what the
prompt point sits on. `tools/run_all_objects.py` reads that file, rewrites the three lines
in the notebook and executes it, which is how the whole set gets re-run after a change to
the pipeline.

Use the notebook to work on one recording and to read what the pipeline does, since every
step's output sits next to the code that produced it. Use the tool to produce the set,
since the notebook can only hold one recording's outputs at a time.

### Finding a prompt point

This is the one step still done by eye, because no automatic rule has been made to work.
Deriving the click from the hand needs the fingertips and the glasses number the 21
landmarks without saying which are which, so the fingertips have to be inferred. Every way
of inferring them moves as the hand opens and closes and the click then lands on a bowl
or on the wearer's arm.

What works:

1. Plot a frame where the object is clear of anything sharing its colour, with real pixel
   coordinates on the axes and a grid over it.
2. Read a coordinate off the object and run SAM once on that point.
3. Judge it by mask area first. On this spoon a good mask is 4,000 to 7,000 pixels. A few
   hundred means you hit a highlight, 20,000 means a bowl, 100,000 or more means the table
   or an arm.
4. Then look at the outline. Area alone will not tell you the mask is on the right object.
5. Then run the pipeline and look at `tools/check_tracking.py <recording>`, because steps 1
   to 4 use SAM on one frame while the pipeline uses SAM 2 over the video and the two do
   not always choose the same object from the same point. On `grip_03b` a point giving a
   clean 7,143 pixel spoon on one frame gave the whole red bowl under the video tracker.

`tools/find_prompt.py <recording>` does steps 1 to 3 by brute force and writes a ranked
contact sheet to `cache/prompt_<recording>.png`, which leaves you steps 4 and 5.

Picking the window matters as much as picking the point. Scooping spends most of its time inside
one bowl and the carry between bowls lasts under a second. A window centred on a carry shows the
room frame correction clearly. A window sitting over a bowl shows the object barely moving, which
is a true result and a useless demonstration.

## Tools

| Tool                                    | What it does                                                                       | Needs recordings       |
| --------------------------------------- | ---------------------------------------------------------------------------------- | ---------------------- |
| `tools/check_recordings.py <files>`     | Validates recordings and writes contact sheets. Run it in the lab.                 | yes                    |
| `tools/check_recordings.py --manifest`  | Regenerates `docs/recordings.md` from what is in `recordings/`.                    | yes                    |
| `tools/find_prompt.py <recording>`      | Searches a recording for usable prompt points and writes a ranked contact sheet.   | yes                    |
| `tools/run_all_objects.py [recordings]` | Runs the object pipeline over everything in `tools/object_runs.csv`.               | yes                    |
| `tools/check_tracking.py <recording>`   | Draws frames with the tracked mask outlined, to see what area cannot tell you.     | no, it reads the cache |
| `tools/object_head_motion.py`           | How far the glasses moved during each pipeline window.                             | yes                    |
| `tools/grasp_intervals.py`              | Finds when the hand closed on something and when it let go.                        | yes                    |
| `tools/object_summary.py`               | Collects every object run into one table and one figure.                           | no                     |
| `tools/render_object_cloud.py`          | Redraws the object cloud figures from the committed npz files.                     | no                     |
| `tools/export_ply.py`                   | Rebuilds the PLY clouds from the same npz files. They are deliberately not in git. | no                     |
| `tools/export_video.py`                 | Exports recordings to shareable mp4s in `videos/`, with timestamps burnt in.       | yes                    |

Regenerate the manifest after adding recordings rather than editing it by hand.

### The order they go in

After a run of the pipeline or after changing it, this is the sequence that brings every
derived file back into agreement:

```bash
python3 tools/run_all_objects.py     # the twelve object runs
python3 tools/object_head_motion.py  # head travel per window, which the summary merges
python3 tools/object_summary.py      # the table and the figure
python3 tools/grasp_intervals.py     # grasp brackets, which read object_runs.csv
```

## Things that will bite you

**Activate the virtual environment before any `aria_gen2` command.** Without it `device
list` still works while every authenticated command fails with a confusing error about no
devices being found.

**Never run `aria_gen2 auth pair` on a laptop that is already paired.** It replaces the
stored certificate and locks you out until somebody with the Companion App re-approves it.
Use `aria_gen2 auth check` to confirm an existing pairing instead.

**Never run `git clean -x` in this repository.** The recordings are ignored rather than
absent, which makes them exactly what that command deletes. The weights and the cache would
come back on their own. The 5.1 GB of recordings would not.

**Never run `aria_gen2 recording delete-all`.** The glasses are shared lab equipment and
hold about thirty five recordings belonging to other people.

**Save figures before calling `plt.show()`.** Show closes the figure, so a savefig after it
writes a blank white image.

## Environment

Python 3.12.14 on macOS with no GPU. The virtual environment lives outside the repository
at `~/projectaria_gen2_python_env`. Every pin in `requirements.txt` was read out of that
environment rather than chosen, so each one is a version that has genuinely worked.
