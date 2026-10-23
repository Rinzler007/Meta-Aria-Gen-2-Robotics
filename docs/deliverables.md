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
| `object_<recording>_cloud.png`       | Four panels: one frame, the object pooled, the path from above and the height            |

Four more files follow from those, written by the tools in step 7 of `docs/running.md`:

| | |
| ------------------------------------- | ------------------------------------------------------------------------- |
| `object_<recording>_pose.csv`          | The 4 by 4 pose per frame, relative to the window's first frame            |
| `object_<recording>_pose.png`          | The turn angle, the axis, the translation and three of the matrices        |
| `object_<recording>_model.npz`         | Every frame pooled into the object's own frame, so the path falls away     |
| `object_<recording>_model_refined.npz` | The same with each frame fitted to the model, written where it is narrower |

The two model files are not in git, for the same reason the PLY clouds are not. Every point
in one is already in the matching `_clouds.npz` and the two tools rebuild the whole set
from those in a few seconds.

Distances are in metres everywhere except the PNG, which is labelled in centimetres
because that is easier to read off a figure.

## The trajectory

`object_<recording>_trajectory.csv` has one row per frame and these columns:

| Column                             | Meaning                                                                   |
| ---------------------------------- | ------------------------------------------------------------------------- |
| `frame`                            | 0 to 119, counting from the start of the window, never from the recording |
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

A robot learning the movement needs the room frame. The device frame is included so that
anybody can check the correction for themselves. Nobody has to take it on trust.

## The point clouds

`object_<recording>_clouds.npz` holds one array per frame plus the two trajectories:

| Key                       | Shape      | Contents                                                             |
| ------------------------- | ---------- | -------------------------------------------------------------------- |
| `frame_000` … `frame_NNN` | `(N, 3)`   | The object's points for that frame, in room coordinates              |
| `trajectory_world`        | `(N, 4)`   | Frame number, then the centre in room coordinates                    |
| `trajectory_device`       | `(N, 5)`   | Frame number, the centre as the glasses see it, then the point count |

`N` differs from frame to frame, from a few hundred on a spoon to a couple of thousand on
a jug, because it depends on how much of the object the two cameras could both see.

```python
import numpy as np
z = np.load("outputs/object_scoop_01_clouds.npz")
frame_60 = z["frame_060"]          # (N, 3) in metres, room coordinates
path = z["trajectory_world"][:, 1:]  # (N, 3) the trajectory on its own
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

## How to read the figure

`object_<recording>_cloud.png` has four panels and they answer two different questions. The
top row is the object. The bottom row is where it went. Keeping them apart is the whole
point, because an earlier version of this figure drew every frame's points at the position
the object occupied in that frame. A hundred and twenty copies of a soup tin laid along its
path makes a smear in which neither the tin nor the path can be seen.

**One frame** is the surface both cameras could see at a single instant. It is thin and it
is only ever one side. There is no depth sensor on these glasses and depth comes from
matching what the two forward cameras each saw, so neither can see round the back. A spoon
gives a few hundred points in a frame and a jug a few thousand.

**The object** is every frame carried back into the object's own frame, where the object
stands still and the path falls away. It is drawn as a density, since a hundred thousand
dots at any readable size paint a solid block. The dark core is the object. The pale halo
is stereo noise, which throws a few points a long way out of every one of these clouds, and
that halo is where the haze in the picture comes from.

**The path from above** and **the height against time** are the trajectory, drawn with no
surface points at all so the line is the only thing to read. The start is a circle and the
finish is a cross.

### What the object comes out as

| Object | Stack, the object and its journey together | Pooled into the object's frame |
| --- | --- | --- |
| Spoons | 34 to 43 cm | 12 to 20 cm |
| Soup tins | 56 to 77 cm | 14 to 16 cm |
| Red bowl, which never moves | 25 cm | 24 cm |
| Jugs | 54 to 60 cm | 45 to 52 cm |

The first three are the right sizes for those objects. The jugs are two to three times too
wide, because a jug turns more than anything else here while being carried and the rotation
comes from the wrist, which is too rough to lay two views of a surface on top of each
other. `tools/object_model_refine.py` fits each frame to the model built so far and takes
about 9 cm off two of the three. They are still too wide.

The bowl barely changes because it never moves, so its stack was already the object.

## The SE(3) pose

`object_<recording>_pose.csv` holds one 4 by 4 matrix per frame:

    T = [ R  t ]      R is 3 by 3, which way the object is turned
        [ 0  1 ]      t is 3 by 1, where the object is

Writing a point as four numbers ending in 1 makes the turn and the shift a single
multiplication, `p' = T p`. A chain of movements is then a product of matrices and undoing
one is an inverse, which is how a measurement moves between frames of reference.

| Column | Meaning |
| --- | --- |
| `frame`, `time_s` | Which frame it is and when it happened |
| `turned_deg` | How far the object has turned since the first frame |
| `axis_x`, `axis_y`, `axis_z` | The axis it turned about, as a unit vector |
| `grip_wander_cm` | How far the object drifts inside the hand's frame across the window |
| `m00` … `m23` | The top three rows of T, read across. The fourth row is always 0 0 0 1 |

Every pose is relative to the window's first frame, so row zero is the identity with no
translation. `object_<recording>_pose.png` draws the angle, the axis, the translation and
three of the matrices themselves.

To check that these really are rigid body transforms:

```bash
python3 tools/object_pose.py --check
```

It reads the committed pose files and tests, on all 1,560 frames, that `R R^T = I`, that
`det R = +1`, that `T(0) = I`, that the angle column matches `arccos((tr R - 1)/2)`, that
the axis is a unit vector, that `T^-1 = [R^T, -R^T t]` undoes `T`, that
`T(a->b) T(b->c) = T(a->c)` and that conjugating a rotation leaves its angle alone. Every
one holds to the precision the csv stores.

That last one is the argument the pose rests on. While the object is gripped it sits at
some fixed offset `X` from the wrist that nobody can measure, so the object's movement is
`X^-1` times the wrist's movement times `X`. Conjugating leaves the trace alone, so it
leaves the angle alone. The object therefore turns by exactly the same angle as the
wrist whatever `X` happens to be. That is what makes the wrist's rotation worth reporting
as the object's.

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
depend only on positions. The steps between them never enter either number, so neither
accumulates this.

**The ratio column is not the object's version of the wrist's 1.41.** Read it alongside
the head motion column beside it. An object on a table owes the head nothing, so turning
your head while it sits still makes the glasses record a large movement for something that
never moved and the room frame conversion then shrinks that movement. On the wrist it
grows it. The ratio therefore measures the conversion mixed with head motion. It says
nothing about the conversion on its own. `tools/object_summary.py` prints this whenever it runs.

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

**A flag is a request to look. It is not a verdict.** Apparent area depends on distance
as much as on identity, so an object carried away from the camera shrinks without anything
going wrong. A 2.5 times change in area is only a 1.6 times change in distance.

**No flag is not a guarantee either.** A mask that moves to a nearby object of similar
size keeps its area and the baseline comes from the opening frames, so a coordinate that was
wrong from the very first frame sets the baseline to the wrong object. Look at the frames
every time.
