# Meta Aria Gen 2 Robotics

Advanced Project II, Stony Brook University.

A person wears head mounted research glasses and handles an object. What comes out is the
path that object travelled through the room together with the 3D points belonging to it.
Everything runs offline on saved files.

**The scope here is the glasses.** Producing those two things from a recording is the whole
task. A robot learning a movement from them is the motivation and a possible later project,
and no part of this repository involves a robot arm.

**`docs/status.md` says where the project stands.** Read that first.

| If you want to know                             | Read                      |
| ----------------------------------------------- | ------------------------- |
| Where the project stands and what to build next | `docs/status.md`          |
| What to run, in what order                      | `docs/running.md`         |
| What the output files hold and how to load them | `docs/deliverables.md`    |
| Which recordings exist and which are usable     | `docs/recordings.md`      |
| How to pair the glasses, record and download    | `docs/glasses_runbook.md` |

The notebooks keep their cell outputs on purpose, so for most questions reading one is
faster than running it.

## What the system is for

A robot that helps someone who needs care has to know how to move its arm to do a task.
Teaching it a movement usually means somebody physically pulling the arm through the motion
while it records, which is slow and needs the robot in the room. A caregiver wearing camera
glasses can instead do the task in the ordinary way and the recording becomes the example.

Dasharadhan, the PhD student who set the scope, kept it deliberately narrow:

> Tracking the object by using SAM to generate the mask is fine. Like you mentioned you can
> use either the location of the hand or the user's gaze to generate the prompts required
> for SAM. We do not need to understand the whole scene, as long as we can track the objects
> which the user interacts with we should be fine. What we need is the trajectory the object
> goes through while the user moves it around and the point cloud corresponding to the
> objects. Also we can record the demonstration and process the data offline to generate
> whatever we need. We do not have to run anything in real time.

So two deliverables per recording, the trajectory and the object point cloud. Understanding
the whole scene is out of scope, which is what makes the rest tractable.

## The glasses

They have no screen and show the wearer nothing. Think of them as a recording device worn
on the face. A chip inside runs three algorithms while recording, so the file holds meaning
as well as pictures: 21 landmarks per hand, eye gaze and VIO, meaning the glasses working
out where they are in the room.

Rates measured from our own recordings rather than read off a specification page:

| Stream               | Rate     |
| -------------------- | -------- |
| `camera-rgb`         | 30.0 fps |
| `handtracking`       | 30.0 Hz  |
| `eyegaze`            | 30.0 Hz  |
| `vio`                | 10.0 Hz  |
| `vio_high_frequency` | 794.1 Hz |

**They never say anything about objects** and **they report no depth at all**, since Gen 2
carries no depth sensor. Those two gaps are the whole of this project. Objects come from
segmentation and depth comes from the two forward facing cameras working as a stereo pair.

Everything stays local. Hand tracking, gaze and pose are all written into the file on the
device, so copying it over the cable gives a complete dataset with nothing uploaded. Meta's
cloud service is an optional accuracy improvement that this project does not use and for
Gen 2 it does not offer eye gaze at all.

## How a recording is stored

One recording is one `.vrs` file. Picture it as a set of tables sharing a single clock: a
table of colour frames, one per camera, one of hand tracking results and so on, every row
carrying a timestamp in nanoseconds from that same clock.

The tables hold different numbers of rows, because the sensors run at different speeds, so
**data can never be lined up by row number.** Line it up by time, asking for the hand
position closest to the moment a given camera frame was taken. Everything else rests on
getting that right.

## The two frames of reference

This is the central idea in the project.

**The device frame** has its origin at the front left camera and moves with the wearer's
head. A cup sitting still on a table changes its device frame coordinates whenever the
wearer looks elsewhere. This is what the glasses report natively.

**The room frame** is fixed. VIO gives the glasses' own position at each moment and
chaining that with a position measured from the glasses takes the head motion back out.

The conversion matters because the head follows the hand. During a reach both move together,
so the recording captures only the difference between them, which is smaller than the real
movement. Across all twelve recordings **the wrist covers 1.41 times more space in the room
than the glasses report**, ranging 1.26 to 1.78, with all twelve pointing the same way and
the four tasks averaging between 1.32 and 1.47. A robot copying the raw recording would
reach short every time.

The measure is the diagonal of the smallest box the wrist stayed inside, which runs 45 to
66 cm in glasses coordinates and 57 to 93 cm in the room. A box is fixed by the extremes
alone, so per sample jitter cannot accumulate inside it, where the median step is about
2 mm. Cumulative path length gives 1.40 independently.

Apply the same conversion to an object and the ratio is not a stable number, because an
object owes the head nothing. Turn your head while a cup sits still and the glasses record
a large movement for something that never moved. For objects, read position rather than
ratio. `tools/object_summary.py` prints the head motion beside every object figure for this
reason.

## The pipeline

`notebooks/object_pipeline.ipynb`, configured by one cell at the top:

```python
RECORDING  = "scoop_01"
START_S    = 7.6
DURATION_S = 4.0
PROMPT     = [1090, 820]
MAX_DEPTH  = 2.0
SEARCH_RADIUS = 0.25
```

Given a recording, a window and one click on the object, it runs these steps.

1. **Export the window** as frames and an mp4, 120 frames at 30 fps.
2. **Segment and track.** SAM 2 takes the click on the first frame and propagates the mask
   through the rest, carrying a memory between frames. Masks are cached, so a second run
   skips this entirely.
3. **Check the mask held.** Area against the opening frames, flagging anything that halves
   or more than doubles.
4. **Rectify the stereo pair** and compute disparity with SGBM.
5. **Unproject** every pixel with a disparity into 3D, discarding anything beyond 2 m.
6. **Keep the object's points** by projecting each one into the RGB camera and testing
   whether it lands inside the mask.
7. **Reject outliers**, keeping points within `SEARCH_RADIUS` of the median. A correct mask
   can still contain wrong depths and stereo fails by putting points far behind the object
   rather than slightly off it.
8. **Convert to room coordinates** using the VIO pose nearest that frame in time.

Steps 2 and 6 are the two halves that matter. The mask says which pixels are the object and
the stereo says how far away each pixel is and the object exists only where those agree.

To run it on another recording, change the three lines at the top. Cache names carry the
window so two windows cannot collide, while the deliverables are named per recording so
there is one current result for each. `tools/object_runs.csv` holds the three choices for
all twelve recordings and `tools/run_all_objects.py` drives the whole set.

## Depth from the stereo pair

The two forward facing CV cameras sit 14.23 cm apart and are splayed 40.05 degrees away
from each other, because the frame is curved and they point outward. Of that baseline,
1.95 cm sits off axis in y and 4.57 cm in z. **This is not a rectified pair as it comes**,
so the ordinary formula turning disparity into depth does not apply to it.

The rectification is built here rather than taken off the shelf. The rectified frame is
constructed from the baseline so its x axis runs along the baseline and both cameras share
one orientation, applied through `distort_by_calibration_and_apply_rotation`, which also
undoes the fisheye distortion. That matters, since these cameras use the FISHEYE624 model
where straight lines bow outward.

It is verified rather than trusted. Orthonormality error comes out at 2.2e-16 and 5.9e-17,
both determinants at 1.0 and the rectified baseline lands on the x axis with an off axis
residual of 6.94e-18 metres.

The rectified pair is a virtual camera at 512 by 512 with a focal length of 246.7, giving a
92.1 degree field of view. SGBM matches along each row to give disparity and focal length
times baseline divided by disparity turns that into metres. About 36 percent of pixels get a
disparity and 31 percent survive the 2 metre cut.

**Accuracy.** Checked against the hand positions the glasses compute on their own chip,
which our code has no hand in. On `scoop_01`, three of four points agreed within 8 mm and
the fourth within 31 mm.

**Range.** Error grows with the square of distance: 2.6 mm at 0.3 m, 7.1 mm at 0.5 m,
28.5 mm at 1 m and 114 mm at 2 m. This camera pair suits handling objects at arm's length
and is no use for mapping a room.

**Where it fails.** Along silhouette edges, where one camera sees past the object and the
other does not and on transparent surfaces, which give the two cameras different things to
match. Both put points far behind the object, which is what step 7 of the pipeline removes.

## What comes out

Four files per recording in `outputs/`, described properly in `docs/deliverables.md`:

- `object_<recording>_trajectory.csv`, the object centre per frame in both frames of reference
- `object_<recording>_clouds.npz`, the per frame point clouds plus both trajectories
- `object_<recording>_cloud.png`, the cloud rendered three ways, coloured by time
- `object_<recording>_cloud_world.ply`, for CloudCompare or MeshLab, rebuilt by `tools/export_ply.py`

Across all twelve recordings and four tasks, `object_summary.csv` and `object_summary.png`
put the runs side by side, `grasp_intervals.csv` holds where each hand closed and let go,
and `wrist_world_frame_summary.csv` holds the hand result.

One thing about the renders misleads people. The shape shown is the object drawn 120 times
over, once per frame, laid along the path it travelled. On `scoop_01` a single frame
measures about 12 cm across while the whole stack measures 34 cm and the difference is
travel. To see the object's shape, look at one frame.

## The notebooks

| Order | File                               | What it does                                                                                 |
| ----- | ---------------------------------- | -------------------------------------------------------------------------------------------- |
| 1     | `vrs_basics_hand_trajectory.ipynb` | Reads a VRS file, measures stream rates, picks the acting hand, pulls out its path and speed |
| 2     | `device_calibration.ipynb`         | Prints the extrinsics the rest of the work depends on                                        |
| 3     | `object_pipeline.ipynb`            | **The pipeline.** One configuration cell at the top                                          |
| 4     | `wrist_world_frame.ipynb`          | Converts the hand path into room coordinates across every recording                          |
| 5     | `activity_segmentation.ipynb`      | Cutting a demonstration out by hand speed                                                    |

The filenames carry no numbers, so the order column tells you how to read them. None depends
on another, so any one can be run on its own. Cell outputs are committed on purpose, being
the record of what was observed.

That has a price worth knowing. Git stores a fresh full copy of a notebook every time a
rerun is committed, so commit a rerun when the outputs have actually changed.

## The tools

| Tool                     | What it does                                                       | Needs recordings |
| ------------------------ | ------------------------------------------------------------------ | ---------------- |
| `check_recordings.py`    | Validates recordings, writes contact sheets, builds the manifest   | yes              |
| `find_prompt.py`         | Searches for usable click points and ranks them on a contact sheet | yes              |
| `run_all_objects.py`     | Runs the pipeline over everything in `object_runs.csv`             | yes              |
| `check_tracking.py`      | Draws frames with the mask outlined, which area alone cannot check | no               |
| `object_head_motion.py`  | How far the glasses moved during each window                       | yes              |
| `grasp_intervals.py`     | Where each hand closed on something and let go                     | yes              |
| `object_summary.py`      | Collects every object run into one table and figure                | no               |
| `render_object_cloud.py` | Redraws the cloud figures from the npz                             | no               |
| `export_ply.py`          | Rebuilds the PLY clouds, which are not in git                      | no               |
| `export_video.py`        | Exports recordings to mp4 with timestamps burnt in                 | yes              |

## Limits worth knowing before you trust a run

**Always look at the frames.** `python3 tools/check_tracking.py <recording>`. The mask area
check catches a mask collapsing onto a highlight or swallowing a table and it cannot catch
a mask moving to a nearby object of similar size, which keeps the area roughly intact. SAM's
own confidence stays at 1.00 through that failure, so the model cannot report it either.

**A click validated on one frame can still fail.** `tools/find_prompt.py` runs SAM on a
single frame while the pipeline runs SAM 2 over the video and they do not always choose the
same object from the same point. A contact sheet panel is a candidate rather than an answer.

**Do not use path length.** Adding up the distance between consecutive frames is dominated
by how steady the centre is, which depends on the object. A spoon's centre moves about 0.2 cm
per frame and a translucent jug's about 1.9 cm, so a jug can come out having travelled 287 cm
while staying inside a 21 cm box. Net displacement and the box diagonal depend only on
positions, so neither accumulates this.

**One object at a time.** Several would mean one click and one track each, which SAM
supports and which is not built.

**Two steps are still manual**, the window and the click. See `docs/status.md` for what
would replace them.

**Depth noise smears each cloud along the viewing direction**, so an object measures deeper
than it is wide. Reducing it needs filtering across neighbouring pixels or averaging across
frames.

## Layout

```
notebooks/        the five notebooks, with their cell outputs kept
outputs/          the deliverables: trajectories, clouds and figures
reports/          the weekly progress reports
docs/             status, running, deliverables, recordings, glasses runbook
tools/            the command line tools listed above
requirements.txt
recordings/       the .vrs files, 5.1 GB, ignored
models/           the YOLO and SAM weights, 431 MB, ignored
cache/            exported frames, mp4s and cached masks, ignored
reference/        papers and the dataset manifest, the papers ignored
vendor/           Meta's unmodified client SDK samples, ignored
```

Every notebook works the repository out from its own location, so this folder can be renamed
or moved without breaking a path.

## What git takes and what it leaves

The working copy runs to about 7.6 GB while the git history is 26 MB. GitHub refuses any
file over 100 MB and several recordings are larger than that, so `.gitignore` excludes
`recordings/`, `models/`, `cache/`, `vendor/`, the pdf files in `reference/` and the PLY
clouds in `outputs/`. Git does not list those, will not stage them and cannot push them.

Each exclusion stands on its own. The recordings are raw data and far too large. The weights
download again in one line. The cache is derived and rebuilds on demand. The vendored samples
ship with the SDK and were never edited. The papers are public downloads, while the 104 KB
dataset manifest beside them is versioned because it records which sequences were used. The
PLY clouds hold nothing the npz files do not.

**Never run `git clean -x` in here.** The data is ignored rather than absent, which makes it
exactly what that command deletes. The weights and the cache would come back. The recordings
would not.

A fresh clone arrives with the code and the deliverables and none of the data. Two tools run
anyway, `render_object_cloud.py` and `object_summary.py`, because what they read is committed.

## Environment

Python 3.12.14 on macOS with no GPU, in a virtual environment outside the repository at
`~/projectaria_gen2_python_env`. Every pin in `requirements.txt` was read out of that
environment rather than chosen, so each one has genuinely worked.

```
python3 -m venv ~/projectaria_gen2_python_env
source ~/projectaria_gen2_python_env/bin/activate
pip install -r requirements.txt
cd notebooks && jupyter notebook
```

SAM 2 propagation over 120 frames takes several minutes on CPU.

**Never run `aria_gen2 auth pair` on a laptop that is already paired.** It replaces the
stored certificate and locks you out until somebody with the Companion App re-approves.
Use `aria_gen2 auth check` instead. **Never run `aria_gen2 recording delete-all`**, since
the glasses are shared lab equipment.
