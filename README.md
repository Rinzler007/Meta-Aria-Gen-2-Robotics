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
`notebooks/Aria_Gen2_04_stereo_depth.ipynb`, and the cell outputs are kept in the
committed notebook so they can be read without rerunning anything.

## Layout

Everything in this repository is either code, a deliverable or a write up. Nothing
here is large and nothing here is regenerable from somewhere else.

```
notebooks/    the four notebooks, with their cell outputs kept
outputs/      the deliverables, which is the trajectory, the clouds and the figures
reports/      the write up for the course
requirements.txt
```

## What is deliberately outside this repository

The project folder that contains this repository holds the heavy things, and none
of them are in git. The notebooks find them by walking up from their own location,
so the arrangement below is not a convention that you can rename freely. It is
wired into the first code cell of each notebook.

```
<project folder>/
    Meta-Aria-Gen-2-Robotics/   this repository
    recordings/                 the .vrs files, about 1.9 GB
    models/                     the YOLO and SAM weights, about 431 MB
    cache/                      exported frames, the mp4 and cached centroids, about 489 MB
    reference/                  papers and dataset manifests, about 36 MB
    vendor/                     Meta's unmodified client SDK samples
```

Each of those is excluded on its own merits. The recordings are the raw data and
they are far too large for git. The weights download again from Ultralytics in a
single line. The cache is entirely derived, so notebook 03 rebuilds the exported
frames and the mp4 from the recording whenever they are missing. The vendored
samples ship with the client SDK and were never edited here.

To set the folders up from a fresh clone, place this repository inside a project
folder and create `recordings`, `models` and `cache` next to it. Notebooks 01, 03
and 04 assert that `recordings` and `models` exist and they stop with a clear
message if either is absent, which is better than quietly writing output into the
wrong place.

### The recordings

| File | Size | What it is |
| --- | --- | --- |
| `pouring_scooping_1_20260918_160639.vrs` | 970 MB | The 67 second pouring and scooping task. Every result in notebooks 03 and 04 comes from this one. |
| `cup_demo_01_20260918_140928.vrs` | 575 MB | A short pick and place demonstration with a cup. |
| `cup_demo_02_20260918_143329.vrs` | 221 MB | The second cup demonstration. |
| `stream_capture_01.vrs` | 16 MB | Captured off the live stream while testing untethered streaming. |
| `aria_gen2_sample_data_1.vrs` | 268 MB | Meta's public sample recording, which needs no credentials and is what notebook 02 reads. |

All four of the first recordings were made on 18 September 2026 using recording
profile 10 rather than the default profile 8, because profile 10 records colour
video at 30 frames per second and that matches the hand tracking rate. The pouring
recording came out at 1185 colour frames against 1184 hand tracking samples, so the
two streams line up one to one. On the public sample the same comparison is 400
against 1200, which is a three to one mismatch that would have had to be resolved
later.

## Environment

The notebooks were run under Python 3.12.14 in a virtual environment that lives
outside the project folder, at `~/projectaria_gen2_python_env`. The versions in
`requirements.txt` were read out of that environment rather than chosen, so they
are versions that have genuinely worked.

```
python3 -m venv <somewhere outside the project>
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
would remove that, and it reports the device pose directly without the chaining
step.

Depth noise smears each cloud along the viewing direction, which is why the spoon
measures deeper than it is wide. Fixing it needs either filtering across
neighbouring pixels or averaging across frames.

Tracking holds for about 100 frames and then slides onto a nearby object, and the
mask score stays high while it does so. The model's own confidence therefore cannot
be used to detect the model's own failure, so a longer sequence needs either
re-prompting or an independent check that the mask still sits where the hand is.

The speed based segmentation in notebook 01 is wrong in a way that matters. The
quiet stretch of the pouring recording is exactly when the task happens, because
scooping is slow, and the fast stretches are walking around. Speed alone finds
locomotion rather than manipulation. Detecting when a hand closes on something would
be the better signal and the hand landmarks needed to build it are already in hand.

Everything so far handles a single object. Several objects would mean one prompt and
one track each, which SAM supports and which has not been built.
