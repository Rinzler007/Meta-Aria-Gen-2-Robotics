# Where this project stands

One page answering four questions. What is the system meant to do, what does it do today,
what does it not do and what to build next.

## The objective

**The scope of this project is the glasses.** Turning a recording into the two deliverables
below is the whole task. A robot learning from those demonstrations is the motivation and
a possible later project. Nothing here involves a robot arm.

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
| Choosing the window                   | Automatic, applied to all 12    |
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
Seen from the wrist's own frame a firmly held object sits at a fixed offset. That
quantity wanders by 1.5 to 5 cm on eleven of the twelve. It reaches 15.6 cm on scoop_03,
whose window straddles the moment the spoon is put down, so the check finds the one case
where the assumption genuinely fails.

An object at rest needs no hand at all. Its pose is one constant matrix. The useful
question is how far the measurement wanders when the answer is known to be zero. The red
bowl in `scoop_01` answers that. Seen from the glasses it appears to travel through a box
13.9 cm across purely because the wearer's head moves. Converted into room coordinates
that falls to 6.1 cm, with a median wander of 0.69 cm. Those are the error bars for every
object position here. The drop from 13.9 to 6.1 is the room frame conversion measured
on a thing that genuinely never moved.

Carried and resting are told apart by whether the object moves further than `STATIC_CM`,
which is drawn from these recordings rather than derived.

Recovering the rotation from the object's own points does not work on this data. Chaining frame to frame fits forward through a window and back should return to
the start. Instead finishes 94 to 105 degrees and over half a metre out. Each fit looks
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

**1. Settle what a demonstration should be measured on.** Windows come from the grip
detection and cover a whole demonstration from grasp to release. `tools/repeatability.py`
asks whether the three takes of a task then give the same answer. The measure matters more
than the window does.

| Task | Box diagonal spread across takes | Net displacement spread |
| --- | --- | --- |
| grip | 3% | 130% |
| pour | 14% | 99% |
| scoop | 66% | 111% |
| pick | 40% | 32% |

Grip at 3 per cent is the strongest repeatability figure the
project has. Three takes of one task, measured independently, land within that of each
other.

Net displacement is the wrong measure for a whole demonstration. Somebody who picks a spoon
up, scoops and puts it back has moved it almost nowhere, so the figure collapses towards
zero and its spread means very little.

The box diagonal survives that. It is uneven across tasks. Grip and pour agree closely
while scoop and pick do not, so a whole demonstration is not automatically the right unit
of comparison. Finding a measure that holds for all four tasks is the open question.

**2. Check the work against ground truth, using the Aria Gen 2 Pilot Dataset.** Nothing
here has been compared with a known correct answer. Depth was checked against the hand
positions the glasses compute themselves, which is independent and covers depth alone. The
object poses have never been checked, because none of our own recordings carries a correct
answer.

The Aria Gen 2 Pilot Dataset is the right source. It was recorded on these same glasses, so
nothing has to be adapted. Three of its data groups answer three separate questions:

| Data group | What it would settle |
| --- | --- |
| `scene/3d_bounding_box.csv` | Whether our object poses are right |
| `depth/depth` | Whether our stereo depth is right, across a whole frame |
| `hand_object_interaction/` | Whether the grip detection agrees with labelled interactions |

Twelve sequences exist and four of them handle objects, which are `cook_0`, `clean_0`,
`eat_0` through `eat_3`. One sequence costs about 2.3 GB, since the recording is 2.2 GB
while the annotations are 1 to 5 MB.

**What blocks it.** The download links in
`reference/AriaGen2PilotDataset_download_urls.json` have expired and return 403 with "URL
signature expired". Fresh ones mean going to Meta's Aria dataset page, accepting the terms
again and downloading a new manifest. That is a few minutes of somebody's time and it
cannot be done from here.

## Where to read next

|                            |                           |
| -------------------------- | ------------------------- |
| How the system works       | `README.md`               |
| What to run                | `docs/running.md`         |
| What the output files hold | `docs/deliverables.md`    |
| Which recordings exist     | `docs/recordings.md`      |
| Using the glasses          | `docs/glasses_runbook.md` |
| Week by week history       | `reports/*.docx`          |
