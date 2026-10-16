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
| Choosing which object to track        | Manual, one click per recording |
| Orientation of the object             | Not produced, position only     |
| Accuracy against known ground truth   | Not measured                    |

The pipeline is `notebooks/object_pipeline.ipynb`. Given a recording, a four second window
and one click on the object, it tracks that object through 120 frames, computes depth from
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

**Two manual steps per recording.** Somebody picks a four second window and clicks on the
object once. Both are fine for twelve recordings and neither survives a caregiver recording
tasks all day.

**The object results are not a repeatability measurement.** The three takes of a task do
not agree closely and the reason is the window rather than the pipeline. Four seconds
chosen by eye for one take sit at a different point in the task from the next, so one
window covers a carry between bowls and another covers a spoon being stirred in one place.
Those are different demonstrations. Aligning the windows is what turns this into a
measurement.

**The trajectory carries position only.** There is no orientation anywhere in the output.
For pouring, the tilt of the jug is the task, and position alone does not describe it.
Whether orientation belongs in the deliverable is worth settling with Dasharadhan, since
his wording asks for the trajectory without saying whether that means position or pose.

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

**1. Settle whether the trajectory should carry orientation.** One question to
Dasharadhan. If it should, that is the largest piece of work outstanding, since it means
estimating the object's pose per frame rather than the centre of its points, and the same
work turns the stacked surfaces into one model of the object.

**2. Place the windows automatically.** `tools/grasp_intervals.py` already finds when the
hand closes on something and lets go, in 8 of the 12 recordings. Starting each window a
fixed time after the grasp begins would make the three takes of a task comparable, which
is the reason three takes of each were recorded. Note that the click is a pixel in the
frame at the window start, so moving a window means finding its prompt again.

**3. Extend grasp detection to objects held with an open hand.** The method watches how
compact the 21 hand landmarks are. It works on a spoon and a jug and declines on a tin,
because a hand stays open around a wide cylinder and there is nothing to detect. Covering
both needs a signal for the hand closing _on an object_ rather than closing in general.

**4. Measure the click rule against ground truth.** HOT3D carries true object poses with
rendered masks across 33 objects. Deriving the click from the hand was tried and does not
transfer between grips and without ground truth there is no way to tell a near miss from
a wild one.

**5. Switch to the `vio_high_frequency` stream.** It runs at 794.1 Hz against the 10 Hz
stream in use, removing the 50 ms gap between a pose and a frame and it reports the device
pose directly without the chaining step. The cheapest real improvement available.

## Where to read next

|                            |                           |
| -------------------------- | ------------------------- |
| How the system works       | `README.md`               |
| What to run                | `docs/running.md`         |
| What the output files hold | `docs/deliverables.md`    |
| Which recordings exist     | `docs/recordings.md`      |
| Using the glasses          | `docs/glasses_runbook.md` |
| Week by week history       | `reports/*.docx`          |
