# What has been done, in order

A dated log of the work, what each stretch established and what it got wrong. The README
explains the project as it stands today. This file explains how it got there, which is the
thing that is hardest to reconstruct after a few weeks away.

The weekly reports in `reports/` are the formal write ups. This is the index to them.

## The goal, which has not changed

A caregiver wears the glasses and performs a task normally. The recording becomes the
example a robot learns the movement from. Dasharadhan set the scope in writing and it is
quoted in full in the README. Two deliverables:

1. The trajectory an object travels through the room.
2. The point cloud belonging to that object.

Understanding the whole scene is explicitly out of scope. Nothing has to run in real time.

## Week 1, 11 to 18 September 2026

Learning the platform and getting the first data. Written up in `reports/Week 1.docx`.

**Established.** The glasses run hand tracking, eye gaze and VIO on a chip inside the
device and write all three into the recording, so the requirement to keep data local was
already met before anything was built. Recording profile 10 puts colour video at 30 fps,
matching the hand tracking rate, which removes a three to one mismatch that profile 8
leaves behind. Streaming works over USB and over a phone hotspot, though starting and
stopping a session still needs a brief cable connection.

**Learned the hard way.** Two published figures disagree with the data. The documentation
says VIO runs at 20 Hz and three recordings measure 10. The specification gives eye
tracking as 5 Hz in one place and 30 in another. The data says 30. Measure the rates
from each recording rather than trusting a specification page.

A speed calculation that assumed a fixed gap between samples produced an impossible
15 m/s, because samples with no hand had been dropped and a multi frame gap was being
treated as a single frame. Use the real elapsed time per step and discard steps that span
a dropout.

**Left undone, which mattered later.** The report's own closing list says "combine the
VIO pose with the hand pose to produce paths in room coordinates. The code for this has
been written but has not been run." It was not run. Week 2 did the conversion for the
object instead. The hand was left in glasses coordinates until October.

## Week 2, 19 to 25 September 2026

Filling the two gaps the glasses leave: they never mention objects and Gen 2 has no depth
sensor. Written up in `reports/Week 2.docx`.

**Object detection does not work for this footage.** YOLOv8n, YOLOv8x, YOLO World and
cropping around the hand. Bowls came back at 0.6 to 0.8. The spoon never passed 0.16 in any
configuration. A detector has to name a thing before it can locate it. A small object
half inside a hand viewed from above is exactly where naming breaks down. Treated as closed.

**Segmentation works immediately.** SAM outlines whatever sits at a point you give it and
never needs to know what the thing is. A single point produced a clean 3,356 pixel mask at
0.90 confidence. `SAM2VideoPredictor` then carried that mask through 136 video frames.

**Depth was built from the two forward cameras.** They sit 14.23 cm apart but are splayed
40.05 degrees, so they are not a usable stereo pair as they come. The rectification was
built by hand and checked numerically, then validated against the glasses' own hand
tracking, which the code has no part in. The right palm agreed to 2 mm.

**The object was put into room coordinates.** Chaining the VIO pose per frame grew the
spoon's x span from 6.0 cm to 18.8 cm, because the wearer was following their own hand with
their head and the two motions were cancelling.

**Both deliverables produced.** `spoon_trajectory.csv`, `spoon_clouds.npz` and a 20,518
point `spoon_cloud_world.ply`, across 100 frames.

**What did not work.** Tracking drifts onto a nearby object after about 100 frames while
its own confidence stays at 1.00, so it never reports its own failure. Automatic prompting
from the hand worked across a window under a centimetre wide, which the report itself
flagged as "fitted to this one grip on this one object". Prompting from the gaze found the
cereal rather than the spoon, which is correct behaviour and turned the choice between them
into a scope question rather than a tuning one.

**Both left hand points failed the depth check**, one by 70.7 cm and one returning nothing,
because they sat on an occlusion boundary. Stereo is unreliable along silhouette edges, and
the silhouette edges of a held object are exactly where those boundaries live.

## Week 3, 8 to 9 October 2026

Dasharadhan raised two things: the arm movement was still in glasses coordinates, and
several tasks had been recorded in one go. He was right about both. The first turned out to be more specific than it first appeared. The object was already in room
coordinates. The hand was not.

**A second dataset.** Twelve recordings on 8 October. Four tasks, three takes each, one
task per file, standing in one place rather than walking to the workstation. Every clip is
two seconds still, the task, two seconds still. `docs/recordings.md` lists them all.

**Tooling.** `tools/check_recordings.py` validates a recording at the bench and generates
the manifest. `tools/render_object_cloud.py` redraws the point cloud figure, which until
now existed in the repository with no code that produced it.

**The hand is now in room coordinates.** `notebooks/wrist_world_frame.ipynb`. Across all
twelve recordings the wrist covers 1.41x more space in the room than the glasses reported,
range 1.26x to 1.78x, with all twelve agreeing and all four tasks landing in the same band.
The measure is the diagonal of the box the wrist stayed inside, which cannot accumulate per
sample jitter. Cumulative path length gives 1.40x independently, which is the corroboration.
Sampling that path at the 10 Hz pose rate gives 1.19x, a floor rather than a correction.

**Why separate recordings mattered, measured.** In the September file the glasses
themselves travelled 27.5 metres and the wrist path spanned 602 cm. A wrist cannot span six
metres, so that was the wearer walking. In the new twelve the head stays within 44 cm.

**Three failures, which is most of the value.**

`grip_03` tracked only the idle left hand for its whole 15 seconds and never found the
right hand holding the spoon, in footage that looks perfectly correct to the eye. A pen
grip appears to defeat the on-device hand tracker. The file is kept as evidence and
`grip_03b` replaces it.

Speed based segmentation is half fixed. `notebooks/activity_segmentation.ipynb`. The
walking confound is genuinely gone, with thirteen blocks becoming a median of two and the
opening quiet period respected in twelve of twelve, with nothing about the method changed.
But the 0.15 m/s threshold did not survive the move, because bench work is slower than
walking. Sweeping down to 0.04 m/s still only reaches about half the expected coverage, so
a fixed global threshold is the wrong shape of answer.

Automatic prompting does not transfer. Tested on `scoop_01`. No offset along either the
wrist to palm or the palm to fingertip direction produced a spoon sized mask on any frame.
Part of the cause is that the fingertips are identified as the five landmarks furthest from
the wrist, which is pose dependent and gave a different set at 8 s and at 10 s of the same
recording.

**Documentation errors corrected.** The jug was never detected at 0.6 to 0.8, its best was
0.40. The point cloud figure renders three views, not two. The git history is 34 MB, not
the 96 MB claimed in two places. The pairing failure that costs you a lab session is now
documented in both the README and the runbook.

**The object pipeline now runs on the new recordings.** `notebooks/object_pipeline.ipynb`
replaces the September pair for everything except the record of how they got there. Its whole
configuration lives in one cell, so pointing it at another recording is an edit there rather
than a hunt through four cells.

On `scoop_01`, tracking the spoon through the carry from the blue bowl to the red one:

| | September | October |
| --- | --- | --- |
| frames with a 3D position | 100 of 136 | **120 of 120** |
| points per frame, median | 187 | **506** |
| accumulated cloud | 20,518 points | **72,710 points** |
| depth check against the device | 2 of 4 points agreed | **4 of 4** |
| mask drift | onto a bowl after ~100 frames | **none** |

The depth result is the one worth dwelling on. September had the left wrist out by 70.7 cm and
the left palm returning nothing, both sitting on an occlusion boundary. On this recording all
four hand points agree, three of them within 8 mm and the worst within 3.1 cm.

The object centre moves through a box 11.9 cm across in glasses coordinates and 18.3 cm across
in the room, a factor of 1.54. That is the same correction the wrist shows at 1.41x, reached
independently from the object rather than from the hand.

**The September outputs were removed.** `spoon_trajectory.csv`, `spoon_clouds.npz`,
`spoon_cloud_world.ply` and three figures all came from the walking recording. They are in the
git history. The two September notebooks are kept, each opening with a note saying what
replaced it, because the detection failure and the rectification work are still findings.

## What the next person should pick up

In rough order of how much they unblock.

**Run the pipeline on the other eleven recordings.** One is done. Each needs a window where the
object is actually moving and a prompt point found by eye, which `docs/running.md` explains how
to do. Three takes of the same task would then show whether the result is repeatable, which is
the reason three takes of each were recorded.

**Settle whether the system tracks the tool or the material.** The hand finds the spoon and
the gaze finds the cereal. Both are correct. The answer is a decision about what the
demonstration is meant to teach, not something that can be tuned.

**Switch to the `vio_high_frequency` stream**, measured at 794.1 Hz against the 10 Hz
stream in use. It removes the 50 ms gap between a pose and a frame and reports the device
pose directly. The cheapest real improvement available.

**Use HOT3D to measure the prompting rule** against ground truth object poses instead of
judging masks by eye. The October test established that a rule judged by eye on one grip
does not survive a second grip, so this is now a specific question rather than a wish.

**Grasp detection** rather than speed, for cutting demonstrations out automatically. It
says which object a demonstration is about rather than only when something moved.

**The gaze driven interface**, where a person looks at an object and a robot fetches it.
The second half of the project. It shares the hardware and very little else.
