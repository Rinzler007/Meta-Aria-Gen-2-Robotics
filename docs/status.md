# Where this project stands

One page answering four questions. What is the system meant to do, what does it do today,
what does it not do and what to build next.

## The objective

**The scope of this project is the glasses.** Turning a recording into the two deliverables
below is the whole task. A robot learning from those demonstrations is the motivation and
a possible later project, and nothing here involves a robot arm.

A caregiver wears Aria Gen 2 glasses and performs a task normally. Dasharadhan set the
scope and it is narrow on purpose:

> What we need is the trajectory the object goes through while the user moves it around
> and the point cloud corresponding to the objects.

So two deliverables per recording and nothing about understanding the rest of the scene.
Everything runs offline on saved files. Nothing has to run in real time.

## What works today

|                                       | Status                          |
| ------------------------------------- | ------------------------------- |
| Object trajectory in room coordinates | Working, 12 of 12 recordings    |
| Object point cloud                    | Working, 12 of 12 recordings    |
| Hand path in room coordinates         | Working, 12 of 12 recordings    |
| Finding when the object is held       | Working on 8 of 12              |
| Choosing which object to track        | Manual, one coordinate typed in |
| SE(3) pose, objects being carried     | Working, 12 of 12 recordings    |
| SE(3) pose, objects at rest           | Working, one fixed pose each    |
| Accuracy against known ground truth   | Not measured                    |

The pipeline is `notebooks/object_pipeline.ipynb`. Given a recording, a four second window
and one pixel coordinate on the object, it tracks it through 120 frames, computes depth from
the two forward facing cameras, keeps the points that fall inside the object's mask and
converts them into room coordinates. It produces the two deliverables and it has done so
for every one of the twelve October recordings without losing its object.

Depth is accurate to within a centimetre over the working range. Checked against the hand
positions the glasses compute on their own chip, which is an independent source: three of
four points agreed within 8 mm and the fourth within 31 mm.

## The measurement that justifies the room frame

The glasses report positions relative to a camera on the wearer's head. During a reach the
head turns to follow the hand, so the recording captures only the difference between the
two movements, which is smaller than the real one. Across all twelve recordings the wrist
covers 1.41 times more space in the room than the glasses report, ranging 1.26 to 1.78.
Cumulative path length gives 1.40 independently.

A robot copying the raw recording would reach short every time. This is the main reason
the room frame conversion exists.

## What is not done

**Two manual steps per recording.** Somebody picks a four second window, then reads a pixel
coordinate on the object off a plotted frame and writes it into `tools/object_runs.csv`.
There is no interface and nothing is clicked. Both are fine for twelve recordings and neither survives a caregiver recording
tasks all day.

**The object results are not a repeatability measurement.** The three takes of a task do
not agree closely and the reason is the window rather than the pipeline. Four seconds
chosen by eye for one take sit at a different point in the task from the next, so one
window covers a carry between bowls and another covers a spoon being stirred in one place.
Those are different demonstrations. Aligning the windows is what turns this into a
measurement.

**The trajectory carries position only, though the rotation now exists beside it.** The
professor asked for an SE(3) pose per object, meaning a 4 by 4 matrix holding rotation and
position together. `tools/object_pose.py` produces the rotation for all twelve recordings,
taken from the wrist pose the glasses compute themselves. While the grip stays firm the
object turns by exactly the angle the wrist turns, because the fixed offset between hand
and object cancels out of a rotation.

The position comes from the object's own points, which the pipeline already places in room
coordinates, so no offset is needed to get it. The tool also checks the grip it depends on.
Seen from the wrist's own frame a firmly held object sits at a fixed offset, and that
quantity wanders by 1.5 to 5 cm on eleven of the twelve. It reaches 15.6 cm on scoop_03,
whose window straddles the moment the spoon is put down, so the check finds the one case
where the assumption genuinely fails.

An object at rest needs no hand at all. Its pose is one constant matrix, and the useful
question is how far the measurement wanders when the answer is known to be zero. The red
bowl in `scoop_01` answers that. Seen from the glasses it appears to travel through a box
13.9 cm across purely because the wearer's head moves. Converted into room coordinates
that falls to 6.1 cm, with a median wander of 0.69 cm. Those are the error bars for every
object position here, and the drop from 13.9 to 6.1 is the room frame conversion measured
on a thing that genuinely never moved.

Carried and resting are told apart by whether the object moves further than `STATIC_CM`,
which is drawn from these recordings rather than derived.

Recovering the rotation from the object's own points was tried first and does not work on
this data. Chaining frame to frame fits forward through a window and back should return to
the start, and instead finishes 94 to 105 degrees and over half a metre out. Each fit looks
good alone, with a median residual under 2 mm, while a spoon or a jug is smooth enough that
a fit slides along its own surface. Over 119 frames that becomes a random walk.

**The point cloud is 120 partial surfaces rather than one object.** Each frame holds the
side of the object the cameras could see at that instant, stacked along the path, so the
shape of the thing and the route it took are tangled together in the same file.

**Accuracy has never been checked against known truth.** Depth was verified against the
hand positions the glasses compute themselves, which is a good independent check on depth
alone. Nothing has verified the object trajectories, because no recording here has ground
truth object poses to compare against.

**The gaze interface has not been started.** A person looks at an object and the system
works out which object they mean. It is the other half of what the glasses can do and it
shares very little with the current pipeline.

## What to build next, in order

**1. Place the windows automatically.** `tools/grasp_intervals.py` finds when the hand takes
hold of something and lets go, across all twelve recordings. Starting each window a
fixed time after the grasp begins would make the three takes of a task comparable, which
is the reason three takes of each were recorded. Note that the prompt is a pixel in the
frame at the window start, so moving a window means finding its prompt again.

**2. Measure the prompt rule against ground truth.** HOT3D carries true object poses with
rendered masks across 33 objects. Deriving the coordinate from the hand was tried and does not
transfer between grips and without ground truth there is no way to tell a near miss from
a wild one.

**Settled: the 0.69 cm position error is the floor for this method.** Three explanations
were tested on the static bowl and two of them were wrong.

The pose stream is not the cause. Swapping the 10 Hz stream for the 794 Hz one closes the
gap between a pose and a frame from 200 ms to 1.33 ms and leaves the typical error at
0.69 cm, exactly where it was.

A viewpoint dependent centre is not the cause either. Pooling all 120 frames into one model
of the bowl and lining each frame up against it leaves the typical error at 0.69 cm and
moves the full box from 6.08 cm to 5.91 cm.

What it is: stereo matching noise. The error points in a random direction, scoring 0.18 for
consistency in the room frame and 0.17 in the device frame, so nothing is systematically
offset. It grows when the head moves, correlating 0.82 with viewing angle, which fits motion
blur and the longer gap to a usable pose. At a range of 65 cm, 0.69 cm is an angle of
0.61 degrees, which is roughly three pixels of disparity in the rectified camera.

Three pixels is close to what block matching gives. Going below it needs sub pixel disparity
refinement or averaging over frames, and neither is worth doing while the objects themselves
move 5 cm to 47 cm. The error is 1.5 to 14 per cent of the movement being measured.

**Not worth doing: switching to the `vio_high_frequency` stream.** It runs at 794.1 Hz
against the 10 Hz stream in use and reports the device pose directly without the chaining
step, so it looked like the cheapest improvement available. It was tested on the static
bowl, which is the one case where the right answer is known. Converting the same frames
with each stream moves the typical error not at all, from 0.69 cm to 0.69 cm, and the worst
frame from 4.62 cm to 4.35 cm. The gap between a pose and a frame falls from 200 ms to
1.33 ms and buys nothing, which is what rules the pose stream out as the cause.

## Where to read next

|                            |                           |
| -------------------------- | ------------------------- |
| How the system works       | `README.md`               |
| What to run                | `docs/running.md`         |
| What the output files hold | `docs/deliverables.md`    |
| Which recordings exist     | `docs/recordings.md`      |
| Using the glasses          | `docs/glasses_runbook.md` |
| Week by week history       | `reports/*.docx`          |
