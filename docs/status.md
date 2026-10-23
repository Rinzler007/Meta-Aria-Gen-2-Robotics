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
| Finding when the hand touches the object | From the object, 67.2% on an outside recording |
| Choosing the window                   | Automatic, applied to all 12    |
| Choosing which object to track        | Manual, one coordinate typed in |
| SE(3) pose, objects being carried     | Working, 12 of 12 recordings    |
| SE(3) pose, objects at rest           | Working, one fixed pose each    |
| One model of the object from many views | Working, 13 of 13 windows     |
| Accuracy against known ground truth   | Grip and prompt checked, poses not |

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
plotted frame and writes it into `tools/object_runs.csv`. There is no interface. Nothing is
clicked. That is fine for twelve recordings. It does not survive a caregiver recording all
day.

Rules for placing it automatically can now be scored, against the Pilot Dataset's labels of
the object a hand is touching. `tools/prompt_rule.py` runs that. The best of them takes the
middle of the hand and steps 1 to 2 cm towards the outermost landmarks, which lands inside
the object 39 per cent of the time.

Two things come out of that. Reaching past the fingertips is wrong, since accuracy falls
steadily the further out you step, down to 9 per cent at 9 cm. A held object overlaps the
hand holding it. And 39 per cent is about seventy per cent of what is reachable, because
the hand's own middle only lands on the labelled hand 56 per cent of the time. Hand
tracking and labels disagree. A hand is often half hidden behind what it holds.

Where the wearer is looking improves on that. `tools/gaze_prompt.py` scores gaze rules the
same way on the same labels. Gaze on its own is poor: the pixel where the eyes converge
lands on the object 14.9 per cent of the time and pushing the direction out to any fixed
distance leaves it at 15. People do not look at the middle of the thing in their hand.

Gaze together with the hand is the best rule the project has. Starting at the middle of the
hand and stepping a short way towards where the eyes are looking lands on the object 46.3
per cent of the time, against 39.6 per cent for the hand alone scored on the same 1,135
frames. The ceiling on those frames is 54 per cent, so the gaze rule reaches 86 per cent of
what is available where the hand alone reaches 73. A small step is what works. Four
centimetres scores 45.5 per cent and eight scores 39.6, so the gaze gives the direction the
object lies in without giving the distance.

Missing more than half the frames is still not good enough to drop a person from the loop.

**The jugs are the weak case for the object model.** Each frame holds the side of the
object the cameras could see, so the shape of the thing and the path it took sit tangled in
the same file. `tools/object_model.py` separates them by carrying every frame's points back
into the object's own frame and it now does that for all thirteen windows. A spoon comes
out 14 to 22 cm across, a soup tin 14 to 16 and the red bowl 24, against stacks of 25 to
77 cm. Those are the right sizes for those objects.

A jug comes out 47 to 52 cm, which is two to three times what a jug measures. The jug is
the object that turns most while it is carried, so it is the one most exposed to the
rotation being rough. The rotation comes from the wrist, which is right about how far the
object turned while being too rough to lay two views of a surface on top of each other. The
grip check in `tools/object_pose.py` shows the object sliding 1.5 to 5 cm inside the hand
across a window and at the 15 cm or so between wrist and object that is around 20 degrees.

`tools/object_model_refine.py` corrects each frame against the model built so far, which
brings all three jugs to 45 cm. It changes the spoons and the tins by a centimetre or two
either way, so the wrist rotation was already good
enough for them. The jugs are still too wide, so this is improved and not finished.

**Grip detection from the hand's shape does not generalise and it has been replaced.** It
was checked against Meta's Aria Gen 2 Pilot Dataset, recorded on the same glasses by
somebody else, whose labels mark a held object frame by frame. On their `cook_0` sequence
it agrees 46.9 per cent of the time while marking 49 per cent of the recording against
their 42. That is guessing. `tools/check_against_pilot.py` runs that comparison.

The problem is not the particular number we read off the hand. `tools/grip_features.py`
scores twelve different things you can measure on 21 landmarks and none clears 59 per cent.
Fitting all twelve together reaches 59.1 per cent on the half of the recording it was
fitted on and 50.5 per cent on the half it was not, so it memorised and learned nothing.
The shape of a hand does not carry whether the hand is holding something.

`tools/grip_from_object.py` stops reading the hand. It measures the distance from the
nearest hand landmark to the nearest point of the object the pipeline is tracking, and
calls it contact below four centimetres. That threshold is a physical distance, so it means
the same thing in anybody's kitchen, where a flatness threshold has to be found inside the
recording it is used on.

`tools/check_contact_against_pilot.py` scores it on their recording by running our tracker
on half an avocado in their kitchen and comparing against their labels for that same
object. Over 137 frames it agrees 67.2 per cent of the time and catches 93.8 per cent of
the frames they mark. It over-calls, marking contact on 73.7 per cent of frames against
their 46.7, because it holds on while the hand lingers near the avocado after setting it
down. One window of one recording is not a general result. It is the first thing in this
project to beat guessing on data from outside the lab.

What it measures is contact and not holding. A hand working inside a stationary bowl passes
the test, which is why the static red bowl reads 75.8 per cent. Asking whether the object
keeps a fixed offset from the wrist was tried as a second test and does not separate the
two, because over a second a still hand beside a still bowl holds just as fixed an offset
as a hand carrying it.

**The object poses have still not been checked against known truth.** The Pilot Dataset
carries 6-DoF poses for 42 objects in `cook_0`. Every one of them is static furniture:
storage, windows, lamps, chairs, tables. That matches what the EFM3D work covers, which is
room scale. It can check static object work. It carries no ground truth for a handheld
object's pose, so the carried object poses remain unchecked.

Depth has an independent check, against the hand positions the glasses compute on their own
chip. That covers depth alone.

**The gaze interface is one measurement, not an interface.** A person looks at an object
and the system works out which object they mean. What exists today is
`tools/gaze_prompt.py`, which shows gaze carries a signal the hand does not: stepping from
the hand towards the gaze beats the hand alone by seven points and reaches 86 per cent of
what is available. Nothing selects an object end to end and nothing runs live.

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

**2. Make the object model work for a jug.** The spoons, tins and the bowl come out at
their real sizes. The jugs come out two to three times too wide and the rotation is why.
`tools/object_model_refine.py` already brings all three to 45 cm by fitting each frame
against the model built so far. It is not enough.

The fits sit a median of 0.7 to 3.0 mm from the model, which is far tighter than the model
is wide. A fit settling snugly in the wrong place is what a smooth surface does, so more
rounds of the same fitting will not help. What would help is a rotation measured from the
object's own points, fitted over the whole window at once. The wrist should have no say in
it and neither should any single pair of frames.

**3. Stop the contact detection over-calling.** It catches 93.8 per cent of the frames
Meta's labels mark and marks 73.7 per cent of frames against their 46.7. The extra frames
are the hand lingering near the object after setting it down. Distance alone cannot tell
those apart.

Whether the object moves with the hand ought to. It does not. The measurement is in
`tools/grip_from_object.py --wander-sweep`. The static red bowl should look the least held
of anything here. It reads among the steadiest at every window length from one second to
six, 1.30 cm at six seconds against 1.48 and 1.67 for two of the carried tins. The number
is dominated by the object's centre shifting as its visible surface changes. Something that
measures the object's motion without going through its centre is what this needs.

**4. Tell one object from another where the work is happening.**
`tools/propose_prompt.py` already finds the right place in almost every window. It picks
the wrong object out of that place whenever the target is a spoon inside a bowl. Nothing
here distinguishes the objects in a cluster. A caregiver's kitchen is clusters all the
way down.

**5. Build the gaze interface.** `tools/gaze_prompt.py` and `tools/propose_prompt.py` show
the signal is there and apply it to a still frame. Nothing turns it into a system somebody
uses. That is the other half of what the glasses can do and it is the largest piece of work
left.

## Ground truth and what it settled

Nothing in this project was compared with a known correct answer until the Aria Gen 2 Pilot
Dataset was brought in. It was recorded on these same glasses, so nothing has to be
adapted. Three of its data groups answer three separate questions:

| Data group | What it settles | Answer |
| --- | --- | --- |
| `hand_object_interaction/` | Whether grip detection agrees with labelled interaction | Checked. Hand shape 46.9%, object distance 67.2% |
| `hand_object_interaction/` | Whether a rule can place the prompt coordinate | Checked. Hand 39.1%, hand with gaze 46.3%, ceiling 54 to 56% |
| `scene/3d_bounding_box.csv` | Whether our object poses are right | Static furniture only, so it cannot check a carried object |
| `depth/depth` | Whether our stereo depth is right across a frame | Not used yet |

Twelve sequences exist and four of them handle objects, which are `cook_0`, `clean_0`,
`eat_0` through `eat_3`. One sequence costs about 2.3 GB, since the recording is 2.2 GB
while the annotations are 1 to 5 MB. `cook_0` is the one downloaded, into
`reference/pilot_cook_0/`, which `.gitignore` keeps out of the repository.

**To get another one.** Go to Meta's Aria Gen 2 Pilot Dataset page, accept the terms and
download the manifest of file links. The links are signed and they expire, so grab one when
you are ready to use it. Put it in `reference/` and the sizes above tell you which sequence
to pull.

**To run our pipeline on one of their recordings.** Link the recording into `recordings/`
under a name the notebook can glob, add a row to `tools/pilot_runs.csv` and run the driver
against a scratch copy of the notebook, so their outputs do not land in the committed one:

```
ln -s "$PWD/reference/pilot_cook_0/cook_0.vrs" recordings/cook0_pilot.vrs
python3 tools/run_all_objects.py --runs tools/pilot_runs.csv \
    --notebook notebooks/_pilot_scratch.ipynb
python3 tools/check_contact_against_pilot.py cook0_avocado reference/pilot_cook_0
```

## Where to read next

|                            |                           |
| -------------------------- | ------------------------- |
| How the system works       | `README.md`               |
| What to run                | `docs/running.md`         |
| What the output files hold | `docs/deliverables.md`    |
| Which recordings exist     | `docs/recordings.md`      |
| Using the glasses          | `docs/glasses_runbook.md` |
| Week by week history       | `reports/*.docx`          |
