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
they are 5.1 GB and `.gitignore` keeps them out. One thing still works:

| Command | What it does | Needs |
| --- | --- | --- |
| `python3 tools/render_object_cloud.py` | Redraws `outputs/object_scoop_01_cloud.png` | `outputs/object_scoop_01_clouds.npz`, which is committed |

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

| Order | Notebook | Needs | Produces | Time |
| --- | --- | --- | --- | --- |
| 1 | `vrs_basics_hand_trajectory.ipynb` | `scoop_01` | `wrist_speed_segmented_clean.png` | 2 min |
| 2 | `device_calibration.ipynb` | `scoop_01` | nothing, it prints and plots | 2 min |
| 3 | `object_pipeline.ipynb` | `scoop_01`, SAM weights | the four `object_scoop_01_*` deliverables | 15 min cold, 3 min with cached masks |
| 4 | `wrist_world_frame.ipynb` | the twelve October recordings plus `pouring_scooping_1` | `wrist_world_frame_summary.png` and `.csv`, one path figure | 10 min |
| 5 | `activity_segmentation.ipynb` | the same thirteen | `activity_segmentation.png` and `.csv` | 10 min |

Two further notebooks, `object_detection.ipynb` and `stereo_depth.ipynb`, are the September
development record rather than part of the pipeline. Each opens with a note saying what replaced
it. Do not run `stereo_depth.ipynb` casually, because it recreates the September deliverables in
`outputs/` under their old `spoon_*` names. Those were removed so they could not be mistaken for
current results.

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

This used to be the main thing standing between the repository and something a new person could
use. The September notebooks spread the recording, the time window, the frame count and the
prompt point across four cells, with the window written into cache filenames.

`object_pipeline.ipynb` now holds all of it in one cell:

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

### Finding a prompt point

This is the one step still done by eye. It has to be, because the automatic rule does not
transfer. Tested on 9 October: no offset along either the wrist to palm or the palm to fingertip
direction produced an object sized mask on any frame of `scoop_01`.

What works:

1. Plot a frame where the object is clear of anything sharing its colour, with real pixel
   coordinates on the axes and a grid over it.
2. Read a coordinate off the object and run SAM once on that point.
3. Judge it by mask area first. On this spoon a good mask is 4,000 to 7,000 pixels. A few
   hundred means you hit a highlight, 20,000 means a bowl, 100,000 or more means the table
   or an arm.
4. Then look at the outline. Area alone will not tell you the mask is on the right object.

Picking the window matters as much as picking the point. Scooping spends most of its time inside
one bowl and the carry between bowls lasts under a second. A window centred on a carry shows the
room frame correction clearly. A window sitting over a bowl shows the object barely moving, which
is a true result and a useless demonstration.

## Tools

| Tool | What it does |
| --- | --- |
| `tools/check_recordings.py <files>` | Validates recordings and writes contact sheets. Run it in the lab. |
| `tools/check_recordings.py --manifest` | Regenerates `docs/recordings.md` from what is in `recordings/`. |
| `tools/render_object_cloud.py` | Redraws the object cloud figure from the committed npz. |

Regenerate the manifest after adding recordings rather than editing it by hand.

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
