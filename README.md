# Meta Aria Gen 2 Robotics

Advanced Project II, Stony Brook University.

Somebody wears camera glasses and does an everyday task with their hands. This turns that
recording into two things. Where the object moved through the room, plus what it looks
like in 3D. Nothing is stuck to the object and nobody labels anything.

The glasses are the whole of this project. A robot learning from these demonstrations is
the reason for doing it and a possible later project. No robot arm is involved here.

## What is in here

| | |
| --- | --- |
| Where the project stands | `docs/status.md` |
| How to run it, step by step | `docs/running.md` |
| What the output files contain | `docs/deliverables.md` |
| Which recordings exist | `docs/recordings.md` |
| Using the glasses | `docs/glasses_runbook.md` |
| Weekly reports | `reports/` |

## The readings

There are twelve recordings, made on 8 October. They cover four tasks with three takes of
each: pouring from a jug, scooping with a spoon, picking up a tin and gripping a spoon
three ways.

| | |
| --- | --- |
| Objects tracked | 13 |
| Frames with a 3D position | 2,789 |
| Points per object | 63,889 to 555,816 |
| Hand movement, room against glasses | 1.41 times, range 1.26 to 1.78 |
| SE(3) pose, every property verified | 1,560 frames, `tools/object_pose.py --check` |
| Contact found from the object | 97 to 100% of frames on the six carried objects |
| The same, scored on an outside recording | 67.2% agreement, 93.8% of their frames caught |
| Position error, measured on a still object | 6.1 cm box |
| Object model width, against a 25 to 77 cm stack | 14 to 24 cm, jugs 47 to 52 |

**The hand reading is the firmest.** The glasses measure from a camera on your head. Your head turns to follow your hand as you reach. Both move at once, so a recording
understates the movement. Measured against the room it comes out 1.41 times
larger. All twelve recordings point the same way.

**The error bar comes from a bowl nobody touched.** A bowl that never moves should measure
zero movement. Through the glasses it appears to travel through a box
13.9 cm across, purely because the wearer's head moves.
Converted into room coordinates that falls to 6.1 cm. The
typical frame is out by 0.69 cm. That is the error on every object position here.

**Whether the three takes of a task agree depends on what you measure.**

| Task | Box diagonal | Net displacement |
| --- | --- | --- |
| grip | 3% | 130% |
| pour | 14% | 99% |
| scoop | 66% | 111% |
| pick | 40% | 32% |

Lower is better. Net displacement is the wrong measure for a whole demonstration, since
picking a spoon up and putting it back moves it nowhere. The box diagonal survives that.
Grip and pour agree closely. Scoop and pick do not.

**Everything here has been checked against somebody else's labels where that was
possible.** Meta's Aria Gen 2 Pilot Dataset was recorded on these same glasses in somebody
else's kitchen and its labels owe nothing to this project.

| | Ours | Theirs says | Ceiling |
| --- | --- | --- | --- |
| Grip from the hand's shape | 46.9% agreement | contact, frame by frame | 100% |
| Grip from the distance to the object | 67.2% agreement | contact with that object | 100% |
| Placing the prompt from the hand | 39.6% on the object | the object being touched | 54% |
| Placing the prompt from hand and gaze | 46.3% on the object | the object being touched | 54% |

The grip figures are two different methods on the same sequence. The first reads the shape
of the hand and performs at chance and no shape you can read off 21 landmarks does better.
The second measures how close the hand comes to the object the pipeline is tracking.

The prompt ceiling is 54 per cent because the hand's own middle only lands on the labelled
hand that often. Hand tracking and labels disagree and a hand is often half hidden behind
what it holds.

## How it works

**The glasses.** Meta Aria Gen 2, worn like normal glasses, no screen. While recording they
save video at 30 frames a second. A chip inside also works out 21 points on each hand plus
where the glasses are in the room. They say nothing about objects and they have no depth
sensor, which is what the rest of this exists to solve.

**Finding the object.** A pixel coordinate on the object goes into the pipeline. SAM 2
outlines the object in that frame and follows the outline through the rest of the window.

**Getting depth.** Distance comes from comparing the two front cameras, the way two eyes
judge distance. They sit 14.23 cm apart and point outward by 40.05 degrees, so the
rectified geometry is built here. Nothing is taken off the shelf. Checked against the hand
positions the glasses work out themselves, three of four points agreed within 8 mm.

**The object.** Every 3D point falling inside the outline belongs to the object. The
glasses' own position track then converts the whole thing from relative to the head into
relative to the room.

**The window.** The pipeline works on one window per recording, running from the moment the
hand closes on the object to the moment it lets go. `tools/grasp_intervals.py` finds those
moments from the shape of the hand.

## The two frames of reference

This is the idea the project turns on.

The **device frame** sits on the glasses and moves with the wearer's head. A cup standing
still changes its device frame position whenever the wearer looks elsewhere. This is what
the glasses report.

The **room frame** stays put. The glasses track their own position, so chaining that with a
position measured from the glasses takes the head movement back out.

A robot copying a raw recording would reach short every time. That is why the conversion is
there.

## Running it

```bash
python3 -m venv ~/projectaria_gen2_python_env
source ~/projectaria_gen2_python_env/bin/activate
pip install -r requirements.txt
```

`docs/running.md` has the full sequence. Two things run on a fresh clone with no
recordings, because what they read is committed:

```bash
python3 tools/object_summary.py     # every run in one table
python3 tools/repeatability.py      # whether the takes agree
```

## What is still manual

Somebody reads a pixel coordinate off a frame and types it in, once per recording. The
window is chosen by code. The best automatic rule starts at the middle of the hand and
steps a few centimetres towards where the wearer is looking, which lands on the object 46
per cent of the time against a ceiling of 54. That is not enough to drop the person.
`tools/prompt_rule.py` scores the rules built from the hand and `tools/gaze_prompt.py`
scores the ones that use the eyes as well.

## Layout

```
notebooks/     two notebooks, cell outputs kept on purpose
outputs/       the deliverables and the figures
tools/         the command line tools
docs/          status, running, deliverables, recordings, runbook
reports/       the weekly reports
recordings/    the .vrs files, 5.1 GB, ignored
models/        the SAM 2 weights, ignored
cache/         frames and masks, rebuilt on demand, ignored
videos/        mp4 exports for sharing, ignored
reference/     papers and dataset manifests, ignored
vendor/        Meta's SDK samples, unmodified, ignored
```

Every notebook works the repository out from its own location, so this folder can be moved
or renamed.

## Things that will bite you

**Look at the frames before trusting a run.** `python3 tools/check_tracking.py <recording>`.
The pipeline checks mask area, which catches a mask collapsing or swallowing the table. It
cannot tell you the outline is on the right object.

**A coordinate checked on one frame can still fail.** `tools/find_prompt.py` runs SAM on a
single frame while the pipeline runs SAM 2 over video. They do not always pick the same
object from the same point.

**Do not use path length.** Adding up the distance between consecutive frames measures how
steady the centre is, not how far the object went. A translucent jug can total 287 cm while
staying inside a 21 cm box.

**Never run `git clean -x` here.** The recordings sit on disk while git ignores them, which
makes them exactly what that command deletes.

**Never run `aria_gen2 auth pair` on a paired laptop.** It replaces the certificate and
locks you out until somebody with the Companion App approves it again.

## Environment

Python 3.12.14 on macOS with no GPU. The virtual environment lives outside the repository
at `~/projectaria_gen2_python_env`. Every pin in `requirements.txt` was read out of that
environment, so each one is a version that has worked.
