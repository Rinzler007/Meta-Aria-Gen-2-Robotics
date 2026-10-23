# What comes out and how to read it

Dasharadhan set the scope as two things per recording. The path an object travels while
somebody moves it around and the point cloud belonging to that object. This file says
exactly what those two things look like on disk, so that somebody working on the robot
side can use them without reading any of our code.

Everything described here lives in `outputs/` and is produced by
`notebooks/object_pipeline.ipynb`. One recording gives four files.

## The four files

| File                                 | What it holds                                                                                      |
| ------------------------------------ | -------------------------------------------------------------------------------------------------- |
| `object_<recording>_trajectory.csv`  | The object centre, frame by frame, in both frames of reference                                     |
| `object_<recording>_clouds.npz`      | The same trajectory plus the per frame point clouds                                                |
| `object_<recording>_cloud_world.ply` | Every point from every frame, stacked, as a plain ASCII PLY. Not in git: run `tools/export_ply.py` |
| `object_<recording>_cloud.png`       | A render of that cloud from three angles, coloured by time                                         |

Distances are in metres everywhere except the PNG, which is labelled in centimetres
because that is easier to read off a figure.

## The trajectory

`object_<recording>_trajectory.csv` has one row per frame and these columns:

| Column                             | Meaning                                                                   |
| ---------------------------------- | ------------------------------------------------------------------------- |
| `frame`                            | 0 to 119, counting from the start of the window rather than the recording |
| `time_s`                           | Seconds from the first colour frame of the recording                      |
| `n_points`                         | How many 3D points were found on the object in this frame                 |
| `device_x`, `device_y`, `device_z` | The object centre as the glasses see it                                   |
| `world_x`, `world_y`, `world_z`    | The object centre in the room                                             |

The two sets of coordinates are the same instant described twice and the difference
between them is the whole point of this project.

**The device frame** has its origin at the front left camera on the glasses and it moves
with the wearer's head. A cup sitting perfectly still on a table changes its device frame
coordinates every time the wearer turns to look elsewhere. This is what the glasses report
natively, so it is what you get if you use their output without thinking about it.

**The room frame** is fixed. It comes from the odometry the glasses run on their own chip
while recording, which tracks where the glasses are. Chaining that with the object position
takes the head motion back out, so an object that does not move keeps the same numbers.

A robot learning the movement needs the room frame. The device frame is included because
having both is what lets anybody check the correction rather than take it on trust.

## The point clouds

`object_<recording>_clouds.npz` holds 122 arrays:

| Key                       | Shape      | Contents                                                             |
| ------------------------- | ---------- | -------------------------------------------------------------------- |
| `frame_000` … `frame_119` | `(N, 3)`   | The object's points for that frame, in room coordinates              |
| `trajectory_world`        | `(120, 4)` | Frame number, then the centre in room coordinates                    |
| `trajectory_device`       | `(120, 5)` | Frame number, the centre as the glasses see it, then the point count |

`N` differs from frame to frame, from a few hundred on a spoon to a couple of thousand on
a jug, because it depends on how much of the object the two cameras could both see.

```python
import numpy as np
z = np.load("outputs/object_scoop_01_clouds.npz")
frame_60 = z["frame_060"]          # (N, 3) in metres, room coordinates
path = z["trajectory_world"][:, 1:]  # (120, 3) the trajectory on its own
```

The PLY carries the same points with the frames concatenated, which is convenient for
looking at and lossy for anything else, since the frame each point came from is gone. Use
the npz for work and the PLY for opening in CloudCompare or MeshLab.

The PLY files are not in git, because they hold nothing the npz does not and they would
double the weight of every commit. One command rebuilds the whole set from the committed
npz files, on a fresh clone with no recordings:

```bash
python3 tools/export_ply.py
```

## What one frame is and what the stack is

This is the one thing that reliably misleads people looking at the render, so it is worth
being plain about.

A single frame holds the surface of the object that both cameras could see at that instant.
It is not the whole object. The back of it never appears, because there is no depth sensor on these
glasses and depth is computed by matching what the two forward facing cameras each saw.
Neither of them can see round the back.

The stack of 120 frames is therefore the object drawn 120 times over, laid out along the
path it travelled. On `scoop_01` any single frame measures about 12 cm across, which is
about right for the scoop end of a spoon with cereal on it, while the whole stack measures
about 34 cm across. The extra is travel. If you want the shape of the object on its own,
look at one frame. If you want the demonstration, you want the stack.

## Across all twelve recordings

`tools/object_summary.py` reads every trajectory in `outputs/` and writes
`outputs/object_summary.csv` and `outputs/object_summary.png`. It needs nothing but the
committed files, so it runs on a fresh clone.

The column worth paying attention to is net displacement in the room frame, meaning where
the object finished relative to where it started.

**The three takes of a task are not yet comparable to each other.** Each window is four
seconds chosen by hand and nothing makes the four seconds picked for one take sit at the
same point in the task as the four seconds picked for the next. One grip window covers a
carry between bowls while another covers a spoon being stirred in one place, which are
different demonstrations and should give different numbers. Comparing takes means placing
the windows at the same point in each, which is what `tools/grasp_intervals.py` makes
possible.

**Do not use path length**, meaning the distance added up step by step along the
trajectory. It is dominated by how steady the centre is from one frame to the next and
that depends on the object. The spoon's centre moves about 0.2 cm between consecutive
frames and the translucent jug's about 1.9 cm, nine times as much, so the jug comes out
having travelled 287 cm while staying inside a 21 cm box. A large transparent object
presents a different set of stereo matchable pixels every frame, so the average of those
points wanders even when the object is nearly still. Net displacement and the box diagonal
depend only on positions rather than on the steps between them, so neither accumulates
this.

**The ratio column is not the object's version of the wrist's 1.41.** Read it alongside
the head motion column beside it. An object on a table owes the head nothing, so turning
your head while it sits still makes the glasses record a large movement for something that
never moved and the room frame conversion then shrinks that movement rather than growing
it. The ratio therefore measures the conversion mixed with head motion rather than the
conversion alone. `tools/object_summary.py` prints this whenever it runs.

## Checking a run before you trust it

Two checks come with every run and they answer different questions.

The notebook's own drift check watches the mask area against the opening frames. It catches
a mask that collapses onto a highlight and a mask that swallows a bowl or the table.

What it cannot see is whether the outline is on the right object, since a mask that slides
from a spoon onto a bowl of similar size keeps its area. For that there is no substitute for
looking:

```bash
python3 tools/check_tracking.py scoop_01
```

That draws eight frames spread across the window with the mask outlined on each, into
`cache/tracking_<recording>_<window>.png`.

**A flag is a request to look rather than a verdict.** Apparent area depends on distance
as much as on identity, so an object carried away from the camera shrinks without anything
going wrong. A 2.5 times change in area is only a 1.6 times change in distance.

**No flag is not a guarantee either.** A mask that moves to a nearby object of similar
size keeps its area and the baseline comes from the opening frames, so a coordinate that was
wrong from the very first frame sets the baseline to the wrong object. Look at the frames
every time.
