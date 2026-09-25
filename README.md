# Meta Aria Gen 2 Robotics

Advanced Project II, Stony Brook University.

The question behind this work is whether a pair of camera glasses can replace the
usual way of teaching a robot a new motion. Normally a person drags the arm through
the movement while it records, which is slow and needs the robot to be present. If a
caregiver can instead wear the glasses, do the task the ordinary way and have the
recording become the example, then the demonstration costs nothing but the doing of
it. That requires the path the hands took and the path the objects took, both in
real units in the real room.

The glasses hand you the hands for free, because hand tracking, eye gaze and device
pose are all computed on the device and written into the recording. They hand you
nothing at all about objects. There is no depth stream on Gen 2 and no object
detection anywhere in the pipeline, so both of those had to be built. That is what
this repository is.

## What it produces

Two things, which are the two that were asked for. The first is the trajectory an
object follows while a person moves it around, given in metres in room coordinates.
The second is the point cloud of that object, one per frame and one accumulated.

Both come out of `notebooks/Aria_Gen2_04_stereo_depth.ipynb` and both land in
`outputs/`.

## Working the glasses

`docs/glasses_runbook.md` holds the commands that were actually used to pair the glasses,
record, download and stream both over the cable and untethered, along with the
troubleshooting that came out of getting it wrong the first time. It is a record of what
worked rather than a copy of the documentation.

## The notebooks

| Notebook | What it does |
| --- | --- |
| `Aria_Gen2_01_vrs_basics_hand_trajectory.ipynb` | Opens a recording, measures the real sampling rate of every stream rather than trusting the documented one, then pulls the wrist out of the hand tracking stream and builds a speed profile from it. |
| `Aria_Gen2_02_device_calibration.ipynb` | Meta's own calibration tutorial, kept because it is where the sensor extrinsics and the fisheye models come from. This one runs on the public sample recording and also runs in Colab. |
| `Aria_Gen2_03_object_detection.ipynb` | The detection attempts, which is to say YOLOv8n, YOLOv8x and YOLO World, then the move to SAM and to SAM2VideoPredictor for propagating a mask through the video. |
| `Aria_Gen2_04_stereo_depth.ipynb` | Rectifies the two front SLAM cameras into a stereo pair, runs SGBM for disparity, converts that to metric depth, unprojects it into a point cloud, keeps only the points falling inside the SAM mask and finally chains the VIO poses to put the result in room coordinates. |

## How the pipeline works

The two forward SLAM cameras sit about 14 cm apart and they are angled roughly 40
degrees away from each other, because the frame is curved and they point outward.
That means they are not a rectified pair, so disparity cannot be turned into depth
until both images have been warped onto a shared plane. Notebook 04 computes that
rotation from the calibration, checks that the baseline really does land on the
image x axis afterwards and only then runs the matching.

The depth was then checked against something the code has no hand in. The glasses
report the wrist and the palm in 3D from their own on device hand tracking, so
projecting those known points into the rectified image and reading the computed
depth at those pixels gives an independent comparison. The palm agreed to 2 mm and
the wrist to 2 cm at roughly 50 cm range. That check is the reason the rest of the
numbers are worth anything.

The range is short and it is short for a reason that is built into the geometry.
Depth error grows with the square of distance, so this pair is good for
manipulation at arm's length and it is no use for mapping a room.

The mask and the depth live in two different cameras, since SAM runs on the RGB
image while the depth comes from the SLAM pair. They are joined by projecting each
3D point into the RGB camera and keeping the ones that land inside the mask.

Chaining the VIO poses turned out to matter far more than expected. In the device
frame the spoon moves about 6 cm in x, while in the room it moves about 19 cm. The
head was following the spoon, so the two motions were cancelling and the device
frame was hiding most of the real travel. Skipping that step would teach a robot a
motion three times smaller than the one the person performed.

All figures in this section come from the notebook runs recorded in
`notebooks/Aria_Gen2_04_stereo_depth.ipynb`. The cell outputs are kept in the
committed notebook, so they can be read without rerunning anything.

## Layout

Everything this project needs now sits inside the repository. Git takes only the part
of it that belongs in git.

```
notebooks/        the four notebooks, with their cell outputs kept
outputs/          the deliverables, which is the trajectory, the clouds and the figures
reports/          the write up for the course
requirements.txt
recordings/       the .vrs files, 1.9 GB, ignored
models/           the YOLO and SAM weights, 431 MB, ignored
cache/            exported frames, the mp4 and cached centroids, 489 MB, ignored
reference/        papers and the dataset manifest, the papers ignored
vendor/           Meta's unmodified client SDK samples, 488 KB, ignored
```

The notebooks find the data by walking up a single level from their own folder, so
every path is relative to this repository. You can rename it or move it anywhere and
nothing below breaks.

## What git takes and what it leaves

The working copy is about 2.9 GB while the git history is 27 MB. The gap between those
two numbers is the whole arrangement. It is worth stating plainly why the data
is safe to keep in here.

GitHub refuses outright any single file over 100 MB. Seven files here are over that
limit, the largest being a 925 MB recording, so a push carrying them would fail rather
than quietly succeed. None of them ever get far enough to be refused, because
`.gitignore` excludes `recordings/`, `models/`, `cache/`, `vendor/` and the pdf files
inside `reference/`. Git does not list those, will not stage them and cannot push
them.

Each exclusion stands on its own merits. The recordings are the raw data and they are
far too large for git. The weights download again from Ultralytics in a single line.
The cache is entirely derived, so notebook 03 rebuilds the exported frames and the mp4
from the recording whenever it finds them missing. The vendored samples ship with the
client SDK and were never edited here. The two papers are public downloads, though the
104 KB dataset manifest sitting beside them is versioned, because it records which
sequences were being looked at.

One consequence follows from all of this and it matters. The data is ignored rather
than absent, which makes it precisely what `git clean -x` is built to delete. Never run
that command in here. The weights and the cache would come back on their own. The
1.9 GB of recordings would not.

A fresh clone therefore arrives with the code and the deliverables and none of the
data. Notebooks 01, 03 and 04 assert that `recordings` and `models` exist and they stop
with a clear message if either is absent, which is better than quietly writing output
into the wrong place.

### The recordings

| File | Size | What it is |
| --- | --- | --- |
| `pouring_scooping_1_20260918_160639.vrs` | 970 MB | The 67 second pouring and scooping task. Every result in notebooks 03 and 04 comes from this one. |
| `cup_demo_01_20260918_140928.vrs` | 575 MB | A short pick and place demonstration with a cup. |
| `cup_demo_02_20260918_143329.vrs` | 221 MB | The second cup demonstration. |
| `stream_capture_01.vrs` | 16 MB | Captured off the live stream while testing untethered streaming. |
| `aria_gen2_sample_data_1.vrs` | 268 MB | Meta's public sample recording, which needs no credentials and is what notebook 02 reads. |

All four of the first recordings were made on 18 September 2026 using recording
profile 10 rather than the default profile 8, because profile 10 records colour video at
30 frames per second and that matches the hand tracking rate. The counts below were read
out of the files rather than off a specification page. Every one of the three lines up
very nearly one to one.

| Recording | Duration | Colour frames | Hand samples | VIO samples |
| --- | --- | --- | --- | --- |
| `cup_demo_01` | 39.5 s | 1185 at 30.0 fps | 1184 at 30.0 Hz | 393 at 10.0 Hz |
| `cup_demo_02` | 15.7 s | 472 at 30.0 fps | 472 at 30.0 Hz | 156 at 9.9 Hz |
| `pouring_scooping_1` | 67.1 s | 2012 at 30.0 fps | 2011 at 30.0 Hz | 670 at 10.0 Hz |

On the public sample the same comparison is 400 colour frames against 1200 hand samples,
a three to one mismatch that would have had to be resolved later.

The VIO column is the reason the trajectory work carries an approximation. Profile 10
lifts the video to 30 frames per second and leaves VIO at 10, so a pose only ever matches
a frame to within 50 ms. The `vio_high_frequency` stream in the same file runs at roughly
800 Hz and would remove that.

## Environment

The notebooks were run under Python 3.12.14 in a virtual environment that lives
outside the repository, at `~/projectaria_gen2_python_env`. The versions in
`requirements.txt` were read out of that environment rather than chosen, so they
are versions that have genuinely worked.

```
python3 -m venv <somewhere outside the repository>
source <that>/bin/activate
pip install -r requirements.txt
```

## What is still open

The automatic prompting is not settled. Walking outward from the palm through the
fingertip centroid does land SAM on the spoon, but only inside a window of about
1.2 cm, which is narrow enough that it is fitted to this one grip rather than being
a rule. Gaze is easier to use, because the device reports an actual 3D gaze point,
though at the moment it was checked that point was on the cereal in the bowl rather
than on the spoon. That is correct behaviour rather than a broken prompt, since a
person scooping looks at what is being scooped. The two signals identify different
objects and choosing between them means first deciding whether the system should
track the tool or the material.

The VIO stream used here runs at 10 samples per second against 30 frame per second
video, so each pose matches a frame only to within 50 ms. There is a
`vio_high_frequency` stream in the same file at roughly 800 samples per second which
would remove that. It also reports the device pose directly without the chaining
step.

Depth noise smears each cloud along the viewing direction, which is why the spoon
measures deeper than it is wide. Fixing it needs either filtering across
neighbouring pixels or averaging across frames.

Tracking holds for about 100 frames and then slides onto a nearby object. The mask
score stays high while it does so. The model's own confidence therefore cannot
be used to detect the model's own failure, so a longer sequence needs either
re-prompting or an independent check that the mask still sits where the hand is.

The speed based segmentation in notebook 01 is wrong in a way that matters. The
quiet stretch of the pouring recording is exactly when the task happens, because
scooping is slow. The fast stretches are walking around. Speed alone finds
locomotion rather than manipulation. Detecting when a hand closes on something would
be the better signal and the hand landmarks needed to build it are already in hand.

Everything so far handles a single object. Several objects would mean one prompt and
one track each, which SAM supports and which has not been built.
