# Where this project stands

This page answers four questions. What is the system meant to do, what does it do today,
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

The pipeline is `notebooks/object_pipeline.ipynb`. Given a recording, a window and one
pixel coordinate on the object, it tracks the object through every frame of that window,
computes depth from the two forward facing cameras, keeps the points falling inside the
object's mask then converts them into room coordinates. The windows come from the grip
detection and run from 87 to 324 frames, covering one demonstration from grasp to
release. It produces the two deliverables and it has done so
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

**One manual step per recording.** Somebody reads a pixel coordinate on the object off a
plotted frame and writes it into `tools/object_runs.csv`. There is no interface. Nothing
is clicked. That is fine for twelve recordings. It does not survive a caregiver recording
tasks all day. Working the coordinate out from the hand does not transfer between grips,
so a dataset with known object positions is needed to measure any rule against.

**The point cloud is a stack of partial surfaces for anything carried.** Each frame holds
the side of the object the cameras could see, so the shape of the thing and the path it
took sit tangled in the same file. `tools/object_model.py` separates them by carrying every
frame's points back into the object's own frame.

It works where the pose is solid and fails where it is not. A resting object has one
constant pose, so the bowl in `scoop_01` narrows from 52.5cm to 24.7cm, which is the
bowl itself. Every carried object comes out wider pooled than stacked, so the tool measures
each one and keeps only those that genuinely improve. It currently keeps 3 of 13.

The rotation is what breaks it. Taking only the path out barely moves the width. Taking the
turning out as well roughly doubles it. The rotation comes from the wrist, which is right
about how far the object turned while being too rough to line surfaces up. The grip check
in `tools/object_pose.py` shows the object sliding 1.5 to 5 cm inside the hand across a
window. At the 15 cm or so between wrist and object that is around 20 degrees of error.

Getting this to work on carried objects needs the object's rotation from the object itself,
which registering frame to frame does not provide on this data.

**Accuracy has never been checked against a known correct answer.** Depth was checked
against the hand positions the glasses compute on their own chip, which is independent and
covers depth alone. The object poses have never been checked, because none of these
recordings carries a correct answer to compare against.

**The gaze interface has not been started.** A person looks at an object. The system works
out which object they mean. It is the other half of what the glasses can do. It shares
very little with this pipeline.

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

**What you need to do first.** Go to Meta's Aria Gen 2 Pilot Dataset page, accept the
terms and download the manifest of file links. The links are signed and they expire, so
grab one when you are ready to use it. Put it in `reference/` and the sizes above tell you
which sequence to pull.

## Where to read next

|                            |                           |
| -------------------------- | ------------------------- |
| How the system works       | `README.md`               |
| What to run                | `docs/running.md`         |
| What the output files hold | `docs/deliverables.md`    |
| Which recordings exist     | `docs/recordings.md`      |
| Using the glasses          | `docs/glasses_runbook.md` |
| Week by week history       | `reports/*.docx`          |
