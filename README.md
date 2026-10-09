# Meta Aria Gen 2 Robotics

Advanced Project II, Stony Brook University.

This repository holds the work on turning a recording made with head mounted
research glasses into something a robot can learn a movement from. A person wears
the glasses and handles an object. What comes out the other side is the path that
object travelled through the room together with the 3D points that belong to it.
Everything runs offline on recorded files. Nothing here has to run in real time.

## Where to start

This README is the long explanation of why each piece exists. Three shorter documents
answer the questions people actually arrive with.

| If you want to know | Read |
| --- | --- |
| What to run, in what order, plus what you get back | `docs/running.md` |
| What has been done so far and what to pick up next | `docs/progress.md` |
| Which recordings exist and which are usable | `docs/recordings.md` |
| How to pair the glasses, record, download and stream | `docs/glasses_runbook.md` |

The notebooks keep their cell outputs on purpose, so for most questions reading one is
faster than running it.

## The problem we are solving

A robot that helps someone who needs care has to know two separate things. It has
to know what the person wants. It also has to know how to move its arm to do it.
Neither one is easy to hand to a robot.

Teaching a robot a new movement usually means someone physically pulling the arm
through the motion while it records. That is slow work. It also needs the robot to
be in the room. Asking the person what they want assumes that they can speak or
press a button, which is not always true.

The idea we are testing is that camera glasses can help with both. A caregiver can
wear the glasses and do the task in the ordinary way, so the recording becomes the
example the robot learns from. If the person being cared for wears them instead,
then where they look can become the way they ask for something. Those are two
separate halves of the project. Only the first half has been built so far.

## What we were asked to build

Two options were put to Dasharadhan, the PhD student who set the scope. The first
was to track only the objects the person handles, using the hands as the trigger.
The second was to understand the whole scene, so the system would know about every
object whether or not anyone touched it. He settled the question:

> Tracking the object by using SAM to generate the mask is fine. Like you mentioned
> you can use either the location of the hand or the user's gaze to generate the
> prompts required for SAM. We do not need to understand the whole scene, as long as
> we can track the objects which the user interacts with we should be fine. What we
> need is the trajectory the object goes through while the user moves it around and
> the point cloud corresponding to the objects. Also we can record the demonstration
> and process the data offline to generate whatever we need. We do not have to run
> anything in real time.

So there are two deliverables. One is the trajectory. The other is the object point
cloud. Understanding the whole scene is out of scope. That decision is what makes
the rest of the work possible, because the second option has no dependable answer
available off the shelf. Meta's own attempt at it, Egocentric Voxel Lifting from the
EFM3D paper, covers room scale furniture such as tables and chairs. It also runs
offline rather than live.

## What the glasses give you

The glasses have no screen. They show the wearer nothing at all. The useful way to
think of them is as a recording device that you wear on your face.

A separate chip inside runs three algorithms while the recording is happening, so
the glasses save meaning as well as pictures. They track the hands with 21 landmarks
each. They track the eyes. They run VIO, which stands for Visual Inertial Odometry
and means the glasses working out where they are in the room. All three results get
written into the recording file next to the raw camera footage.

These are the rates measured from our own pouring recording rather than read off a
specification page.

| Stream               | Samples | Rate     |
| -------------------- | ------- | -------- |
| `camera-rgb`         | 2012    | 30.0 fps |
| `handtracking`       | 2011    | 30.0 Hz  |
| `eyegaze`            | 2012    | 30.0 Hz  |
| `vio`                | 670     | 10.0 Hz  |
| `vio_high_frequency` | 52295   | 794.1 Hz |

## What the glasses do not give you

The glasses never say anything about objects. They will not tell you that a spoon is
in the picture. They will not tell you how far away anything is, because Gen 2 has no
depth stream at all. Those two gaps turned out to be the whole of this project.

## Why none of this needs the cloud

The platform splits into three parts. The glasses record and run the algorithms above.
The Client SDK on the laptop pairs with the device, starts recordings, downloads files
and receives a live stream. Machine Perception Services is Meta's cloud, where you
upload a recording and get more accurate results back.

The part that mattered is that the requirement to keep our data local was already met
before we did anything. Hand tracking, gaze and pose all sit inside the file on the
device, so copying that file over the cable gives a complete local dataset with
nothing uploaded anywhere. We confirmed this by listing the streams and finding
`handtracking`, `vio`, `vio_high_frequency` and `eyegaze` among the camera data. The
cloud service is an optional accuracy improvement rather than something we depend on.
For Gen 2 it does not offer eye gaze at all, so gaze can only ever come from the
device itself.

## How a recording is stored

Everything from one recording goes into a single file ending in `.vrs`. A helpful way
to picture it is a set of tables that all share one clock. There is a table of colour
frames, a table for each of the other cameras, a table of hand tracking results and so
on. Every row carries a timestamp in nanoseconds taken from that same clock.

The tables do not hold the same number of rows, because the sensors run at different
speeds. This means you can never line the data up by row number. You have to line it
up by time instead, by asking for the hand position closest to the moment a particular
camera frame was taken. Getting that right is what everything else rests on.

## The recordings we made

Three recordings were captured over USB on 18 September 2026. The counts below were
read out of the files.

| Recording            | Duration | Colour frames    | Hand samples    | VIO samples    |
| -------------------- | -------- | ---------------- | --------------- | -------------- |
| `cup_demo_01`        | 39.5 s   | 1185 at 30.0 fps | 1184 at 30.0 Hz | 393 at 10.0 Hz |
| `cup_demo_02`        | 15.7 s   | 472 at 30.0 fps  | 472 at 30.0 Hz  | 156 at 10.0 Hz |
| `pouring_scooping_1` | 67.0 s   | 2012 at 30.0 fps | 2011 at 30.0 Hz | 670 at 10.0 Hz |

We chose recording profile 10 over the default profile 8. A profile decides which
sensors are switched on and at what rate. Profile 10 records colour video at 30 frames
per second, which matches the rate the hands are tracked at. The result is very nearly
one hand pose for every frame. On Meta's public sample recording the same comparison
comes out at 400 colour frames against 1200 hand samples, which is a three to one
mismatch. Picking the profile before recording removed that problem instead of leaving
us to solve it afterwards.

`pouring_scooping_1` is the recording every later result comes from. The task runs from
roughly 18 s to 37 s. The tracked window is 100 frames starting at 32.5 s.

A playback of that recording is here, which is the clip shared with the group:

[PouringScooping.mov](https://drive.google.com/file/d/114BMa6YgSmGdRxVtgiFzYJ7MuxKH_KTR/view?usp=share_link)

The `.vrs` files themselves are far too large for git, so this video is the quickest way
to see what the task actually looked like before reading any of the numbers below.

## The recordings we made the second time

Twelve more were captured on 8 October 2026, after Dasharadhan pointed out two problems with
the first set. The arm movement was still being reported relative to a moving head, and
several tasks had been performed in one recording rather than one each.

The second set fixes both. Four tasks, three takes each, one task per file, every one made
standing in one spot at the workstation rather than walking to it.

| Task              | Files                             | What happens                                     |
| ----------------- | --------------------------------- | ------------------------------------------------ |
| Pick and place    | `pick_01` to `pick_03`            | A tin is moved across the table. No tool at all.  |
| Pour              | `pour_01` to `pour_03`            | A jug is lifted, poured into a bowl, set down.    |
| Scoop             | `scoop_01` to `scoop_03`          | The September task again, recorded cleanly.       |
| Grip              | `grip_01`, `grip_02`, `grip_03b`  | Scooping with three deliberately different holds. |

Each one runs 10 to 34 seconds and begins and ends with two seconds of stillness, hands flat
on the table. Those quiet periods are not padding. They give a clean baseline on either side
of the action, which is what any later attempt at cutting demonstrations out automatically
will need.

`grip_03` is kept but excluded. The device tracked only the idle left hand for its whole
15 seconds and never once found the right hand holding the spoon, in footage that looks
perfectly correct to the eye. A pen grip appears to defeat the on-device hand tracker, which
is worth knowing, so the file stays as evidence and `grip_03b` replaces it.

`docs/recordings.md` lists every recording with its duration, which hand was doing the work,
how good the tracking and the pose were and whether it is usable. It is generated by
`tools/check_recordings.py --manifest` rather than written by hand, so it cannot drift away
from what is actually on disk.

### Watching them

The `.vrs` files are gigabytes and nothing outside this project opens them, so each recording
is also exported as an mp4. `tools/export_video.py` rebuilds the whole set from the recordings
in a couple of minutes, at half resolution with the timestamp burnt into the corner.

That timestamp is the point of them. Every result here is quoted against a time within a
recording, for eg. the carry in `scoop_01` running from 7.2 s to 7.8 s and the pipeline window
starting at 7.6 s, so a clip without a clock cannot be checked against any of it.

**All twelve are here:** [October recordings on Drive](https://drive.google.com/drive/folders/1L0lLAV54Fm30vN5Cqwuc7e3UM32n7d_4?usp=sharing)

| Recording | Length | What happens |
| --- | --- | --- |
| `scoop_01` | 26.6 s | The task the pipeline runs on. Scoops from the blue bowl, carries at 7.2 to 7.8 s, works in the red bowl, carries back at about 11.5 s. |
| `scoop_02` | 34.4 s | The longest take. Same task. |
| `scoop_03` | 21.7 s | Same task, third take. |
| `pour_01` to `pour_03` | 14 to 22 s | A jug is lifted, poured into a bowl and set down. |
| `pick_01` to `pick_03` | 10 to 11 s | A tin is moved across the table. No tool involved. |
| `grip_01`, `grip_02`, `grip_03b` | 13 to 20 s | Scooping with three deliberately different holds, to test whether the prompting rule survives a changed grip. |

The videos are not in git. They are 44 MB in total and `tools/export_video.py` remakes them
on demand, so `.gitignore` excludes `videos/`.

## What the recordings told us

The two cup recordings found both hands in almost every sample, with median confidence at
0.9998. `cup_demo_02` never drops below 0.9990 on either hand. `cup_demo_01` is nearly as
clean, though its left hand does dip, with 43 samples of 1180 below 0.999 and a worst case
of 0.54. That answered a question the public sample had raised, since the sample managed
96 percent for one hand and 71 percent for the other. Dropouts are not a fixed limit of
the hardware. They depend mostly on whether the wearer keeps their hands in view, which
is something we can ask a person to do.

The pouring recording is harder work and it taught us more. Detection falls to about 82
percent. Confidence drops as low as 0.688. There is one stretch of 164 consecutive frames
with no left hand at all, which is 5.5 seconds. That gap is far too long to fill in by
guessing, so any real segmentation step would have to end the demonstration there
rather than bridge across it. The short clean recordings had hidden this problem and
the longer task brought it out.

Two published figures also disagreed with the data. The documentation says on device
VIO runs at 20 samples per second. Three recordings now measure 10. The specification
gives eye tracking as 5 per second in one place and 30 in another. The data says 30.
This is why we measure the rates from each recording rather than assuming them.

## Streaming and working without the cable

Streaming over the USB cable works. The default streaming profile carries pose, gaze and
hand tracking alongside the camera images. The supplied viewer shows all of it live.
The SDK also ships an example that hands each kind of data to a callback in Python,
which is where our own code can be attached.

Wireless streaming works too. We put the glasses on a phone hotspot, joined the laptop
to the same network, started the stream over the cable then pulled the cable out. The
data kept flowing. Message batching has to be set when streaming wirelessly, because the
radio generates more heat and the device throttles at 42 degrees.

Control still needs the cable. With the glasses on the same network and the cable
removed, the command that lists devices reports that none were found. Starting a session
and stopping it need a brief USB connection even when the data itself travels over wifi.
Campus networks are not a route either, since Meta state that the SDK does not support
corporate, university or public networks. The glasses can run their own hotspot, which
takes the phone out of the picture as well.

`docs/glasses_runbook.md` has every command used to pair, record, download and stream,
along with the troubleshooting that came out of getting it wrong the first time.

## Connecting when this laptop has been paired before

Pairing is stored on the laptop rather than on the glasses, so it survives rebooting,
unplugging and leaving the device alone for weeks. A laptop that has been paired once stays
paired. Reconnecting on a later day is only these two commands.

```bash
aria_gen2 device list
aria_gen2 auth check
```

`device list` printing the serial and an address tells you the cable is working. `auth check`
coming back clean tells you the stored certificate is still trusted. Once both pass you can go
straight to recording.

Do not run `aria_gen2 auth pair` at this point. The pairing lives in
`~/.aria/tls-client-certs/<serial>/` as a private key together with a self signed certificate.
`auth pair` replaces both with freshly generated ones. The glasses only trust the certificate
they were introduced to, so the new one means nothing to them and every later command dies on a
TLS failure reading `Failed to read data from socket: asio.ssl error`. The old certificate is
overwritten rather than kept, so there is nothing to put back unless the machine happens to be
backed up.

Recovering needs the Companion App, because approving a certificate is the one step that happens
on the phone rather than on the laptop. Whoever holds the app has to be with the glasses while
you run `aria_gen2 auth pair` again so that they can approve it. If the half finished attempt
leaves the local state confused, clear it with `aria_gen2 auth remove-certs` and pair again. On
shared lab glasses this can cost a whole session, since the person holding the phone may not be
in the building.

## Object detection, which did not work

Detection is the obvious first idea, so we gave it a proper try. We started with
YOLOv8n. We moved to YOLOv8x when the small model gave nothing useful. We then tried
YOLO World so that we could set the class names ourselves instead of being stuck with
the 80 categories in COCO. We also cropped a region around the hand and ran detection on
just that piece, so the object would fill more of the frame.

The containers came out fine. Bowls were found reliably at 0.6 to 0.8 confidence with the
large model. The jug never did better than 0.40, reached only under YOLO World where we could
name it ourselves. YOLOv8x has no jug class at all and reported a `bottle` at 0.48 instead. The spoon never worked. It never passed 0.16 confidence
in any configuration and the box was never really sitting on it. In some runs the model
confidently found things that were not in the picture at all, including a chair reported
as a toilet and bowls reported as donuts.

The reason is a mismatch between our footage and the pictures these models were trained
on. The spoon is small in the frame. It is half inside a hand while it is being held.
The glasses look straight down at the table. Almost nothing in the training data looks
like that. A detector has to name a thing before it can locate it. A hand wrapped around
a small object is exactly where naming breaks down. Adjusting a threshold cannot
fix this, so we treat the question as closed.

## Segmentation, which worked straight away

SAM stands for Segment Anything Model and it works on a different principle. Instead of
asking it to recognise anything, you give it one position in the image. It then works out
the exact outline of whatever sits at that spot. It never needs to know that the thing is
a spoon. What comes back is a mask, which is a yes or no for every pixel.

A single point produced a clean mask at 0.90 confidence where every detector had failed.

One detail is worth keeping straight. Nobody clicked with a mouse. The notebook contains
`points=[[1052, 780]]`, a coordinate read off a plot with the axes turned on then typed
in by hand. The limitation is the same either way, which is that something outside the
system has to name the position before any of this can start.

## Following the object through the video

`SAM2VideoPredictor` carries a mask forward through video on its own. You give it the
prompt on the first frame and it propagates from there.

Two practical steps were needed. The relevant stretch of the recording was exported as
individual frames. Those frames were then encoded into an mp4, because the predictor
counts frames through the video source and that counter only exists for a real video
file rather than a folder of images.

It returned a mask on all 136 frames. Looking at the overlays showed it correctly on the
spoon for roughly the first 100, then drifting onto a bowl once the wearer stood up and
the spoon left the view. The mask score stayed at 1.00 all the way through that drift.
The model's own confidence therefore cannot tell us when the model has gone wrong.

That gave us a path, although it was a path in pixels. Because the camera sits on a head,
an object standing perfectly still still appears to travel across the frame as the wearer
turns. Getting rid of that is what the rest of the pipeline does.

## Depth, built from the stereo pair

The two forward facing CV cameras sit 14.23 cm apart. The surprise is that they are also
splayed 40.05 degrees away from each other, because the frame is curved and they point
outward. Of that baseline, 1.95 cm sits off axis in y and 4.57 cm sits off axis in z. So
this is not a rectified pair as it comes. The ordinary formula that turns disparity into
depth does not apply to it.

We built the rectification ourselves. The rectified frame is constructed straight from the
baseline so that its x axis runs along the baseline and both cameras end up sharing one
orientation. It is applied through `distort_by_calibration_and_apply_rotation`, whose
docstring confirms that it can be used for stereo rectification. That call also undoes the
fisheye distortion at the same time, which matters because these cameras use the FISHEYE624
model where straight lines bow outward.

Then we checked the result instead of trusting it. The orthonormality error came out at
2.2e-16 for the left and 5.9e-17 for the right. Both determinants came out at 1.0. The
rectified baseline landed on the x axis with an off axis residual of 6.94e-18 metres. We
also checked it by eye, drawing horizontal lines across both rectified images and confirming
that the same features sat between the same lines.

The rectified pair is a virtual camera we invent, set at 512 by 512 with a focal length of
246.7, which gives a 92.1 degree field of view. With the images lined up, SGBM from OpenCV
matches along each row to give disparity. Focal length times baseline divided by disparity
turns that into metres.

Only 37.2 percent of pixels get a disparity at all. Once depth beyond 2 metres is thrown
away, 32.7 percent remain.

## Checking the depth against something independent

A depth map can look completely sensible while being wrong by a scale factor or an offset.
So we checked it against something our own code has no hand in. The glasses already report
the wrist and the palm in 3D, worked out on the device. Projecting those known points into
our rectified image and reading our computed depth at those same pixels gives an honest
comparison. Four points were tested.

| Point       | Truth   | Our stereo      | Error         |
| ----------- | ------- | --------------- | ------------- |
| right palm  | 0.491 m | 0.489 m         | -0.002 m      |
| right wrist | 0.461 m | 0.481 m         | +0.020 m      |
| left wrist  | 0.458 m | 1.165 m         | +0.707 m      |
| left palm   | 0.480 m | no depth nearby | none returned |

Two of the four agreed closely, to 2 mm and to 2 cm. One was wrong by 70.7 cm, which is our
stereo reporting two and a half times the true distance. One returned nothing at all.

Both left hand points sit on an occlusion boundary, which is a place where the right camera
cannot see what the left camera sees. Stereo is always unreliable along silhouette edges.
That bounds how far the good result travels, because the silhouette edges of a held object
are exactly where those boundaries live.

The useful range follows from the geometry rather than from experiment. Error grows with the
square of distance, so it comes to 2.6 mm at 0.3 m, 7.1 mm at 0.5 m, 28.5 mm at 1 m and
114 mm at 2 m. This camera pair suits picking things up at arm's length. It is no use for
mapping a room.

## From a depth map to the object on its own

Unprojecting every valid pixel gives 85,830 points for the inspected frame. They arrive in
the device frame, which is the front left CV camera. We checked that conversion too. The
nearest point in the cloud sits 15.6 mm from the wrist position the device reported.

The mask lives in the RGB image while the cloud came from the CV cameras. Those two sit in
different places on the frame. We join them by projecting each 3D point into the RGB camera
then keeping only the ones that land inside the mask. Everything else is table and background
and it gets thrown away.

On the inspected frame a 3,356 pixel mask keeps 244 points. Their centre sits 0.687 m from
the glasses with an extent of 4.5 by 5.3 by 9.4 cm, which places it 25.7 cm from the right
wrist. The mask covers the scoop end of the spoon rather than the whole thing, which is why
the centre sits that far from the hand.

We then tested whether the tabletop behind the spoon was leaking in, since a point behind an
object projects into the same place from the camera's point of view. The distances formed one
tight cluster running from 0.674 m to 0.705 m and all 244 points were kept, so nothing leaked.

## Putting the path in the room

Everything up to here is measured from the wearer's face. VIO tells us where the glasses were
at each moment, so chaining that pose with the object position per frame converts the whole
path into room coordinates. 660 of the 670 VIO poses passed both quality checks and all 100
frames were placed.

The difference is large.

| Frame  | x span  | y span  | z span  |
| ------ | ------- | ------- | ------- |
| device | 0.060 m | 0.084 m | 0.165 m |
| room   | 0.188 m | 0.182 m | 0.188 m |

In the device frame the spoon spans 6.0 cm in x. In the room it spans 18.8 cm. The wearer was
following the spoon with their head, so the head motion and the hand motion largely cancelled
each other out and the device frame was hiding two thirds of the real travel. Leaving this step
out would teach a robot a movement three times smaller than the one the person actually made.

## Putting the hand in the room

The section above does this for the object. It was never done for the hand. The Week 1
report says so plainly in its own closing list: the code was written but not run. So the arm
movement stayed in glasses coordinates until October, which is exactly what Dasharadhan
noticed. `wrist_world_frame.ipynb` fixes it and measures the correction across all twelve
October recordings rather than asserting it from one.

**The wrist covers 1.41 times more space in the room than the glasses reported.** The range
runs from 1.26x to 1.78x and all twelve point the same way, with the four tasks averaging
between 1.32x and 1.47x, so no single task carries the result.

The measure is the diagonal of the smallest box the wrist stayed inside, which runs from 45
to 66 cm in glasses coordinates and 57 to 93 cm in the room. We lead with a box rather than
the distance travelled because a box is fixed by the extremes alone, so per sample jitter
cannot accumulate inside it, while the median step here is only about 2 mm. Cumulative path
length gives 1.40x, which is the corroboration that matters. Sampling that path every third
frame to match the 10 Hz pose rate gives 1.19x. That is a floor rather than a correction,
since chording across a curve throws away real movement along with the noise.

One number from that notebook invites a misreading. The distance travelled reaches 465 cm on
`scoop_02`, which sounds absurd for an arm until you remember it is every small movement
across 34 seconds added together. The straight line from where the wrist started to where it
finished is 9.6 cm.

## Prompting SAM automatically

Dasharadhan suggested using the hand position or the gaze to generate the prompt, so that
nobody has to point out the object by hand. We tried both. They turn out to point at different
things.

For the hand we first had to work out the landmark numbering, because it is not the one we
recognised. The device reports the wrist and the palm through their own methods, so whichever
landmark sits closest to each of those is the one we want. Landmark 5 is the wrist and landmark
20 is the palm, both at 0.0 mm, which means those methods return those landmarks exactly.
Sorting the rest by distance from the wrist showed the five furthest out to be the fingertips,
which are landmarks 1, 10, 0, 9 and 12.

That last step does not hold up. It was tested on 9 October. "The five furthest from the
wrist" is a statement about the hand's pose at one instant rather than an anatomical fact, so
the set it returns moves. On `scoop_01` it gives 0, 7, 9, 10 and 12 at eight seconds and
1, 9, 10, 12 and 13 two seconds later, within the same recording. The direction it defines
wobbles with it, which is part of why the prompting below does not transfer.

We take the centroid of those five fingertips then walk outward along the line running from the
palm through that centroid, because a held object continues past the fingers rather than sitting
between them. The palm to centroid distance is 5.0 cm. Offsets of 2.4 cm, 2.8 cm and 3.2 cm past
the centroid all land on the spoon and give masks close in size to the 3,356 pixels we got by
prompting manually. At 3.6 cm the mask jumps to the whole bowl. So the rule holds across at least
0.8 cm and it fails somewhere in the 0.4 cm before 3.6. A window that narrow is fitted to this
one grip on this one object rather than being a rule we could rely on elsewhere.

For gaze the device reports a field called `spatial_gaze_point_in_cpf`, which is the actual 3D
point where the gaze lands rather than only a direction. CPF stands for Central Pupil Frame, so
the point has to be moved into the device frame first using `get_transform_device_cpf()`. Once
converted and projected into the image, the gaze point sat 12.6 cm away from the spoon and SAM
returned an 18,238 pixel mask on the cereal inside the bowl.

That is the right behaviour rather than a broken prompt. When you scoop something you look at
what you are scooping and not at the tool in your hand. The hand tells us where the tool is.
The gaze tells us what the tool is being used on. Choosing between them is not a tuning
decision. It is a question about what the system is for. It is also the same scope question
arriving a second time from the technical end.

## What the pipeline produces

Everything below lives in `outputs/` and comes from `object_pipeline.ipynb` run on `scoop_01`,
the October re-recording of the scooping task. The counts were read back out of the files.

- `object_scoop_01_trajectory.csv` holds 120 rows, one per frame, carrying the frame number,
  the timestamp, the number of points found on that frame and the object centre in both the
  device frame and the room frame.
- `object_scoop_01_clouds.npz` holds 120 per frame clouds along with both trajectory arrays.
- `object_scoop_01_cloud_world.ply` carries 72,710 vertices. It opens in CloudCompare or MeshLab
  without needing any of our code.
- `object_scoop_01_cloud.png` renders that cloud three ways, in perspective, from the side and
  from above, coloured by frame number so the spoon can be seen descending into the bowl. The red
  line is the object centre, which is the trajectory drawn inside its own point cloud. It is
  drawn by `tools/render_object_cloud.py`, which reads the npz rather than the recording, so a
  fresh clone can regenerate it with no data download and no model weights.
- `wrist_world_frame_summary.png` and its csv are the hand result across all twelve recordings.
- `activity_segmentation.png` and its csv are the segmentation test.
- `wrist_speed_segmented_clean.png` is the wrist speed profile with the activity threshold on it.

Every one of the 120 frames produced a 3D position, where the September pass managed 100 of
136 before the mask slid onto a bowl. The point count per frame runs from 396 to 925 with a
median of 506, against a median of 187 in September, so the object is sampled far more densely.

Accumulated in room coordinates the cloud spans 17 cm by 12 cm by 27 cm at its
full extent. Those figures are worth quoting carefully, because depth noise throws a handful of
points a long way out. Across the middle 98 percent it measures 12 by 9 by 15
cm. Quote the full span for a bounding box and the robust one for shape.

The object centre moves through a box 11.9 cm across in glasses coordinates and 18.3 cm
across in the room, a factor of 1.54. That is the same correction the hand shows at 1.41x,
arrived at independently from the object rather than from the wrist.

## The notebooks

| Order | File                               | What it does                                                                                                              |
| ----- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| 1     | `vrs_basics_hand_trajectory.ipynb` | Reads a VRS file, measures the real stream rates, picks whichever hand did the work then pulls out its path and speed.   |
| 2     | `device_calibration.ipynb`         | Meta's calibration tutorial, pointed at our own recording so it prints the extrinsics the rest of the work depends on.   |
| 3     | `object_pipeline.ipynb`            | **The pipeline.** Prompt, track, stereo depth, object cloud, room coordinates. One configuration cell at the top.        |
| 4     | `wrist_world_frame.ipynb`          | Converts the hand path out of glasses coordinates into room coordinates, across every recording.                         |
| 5     | `activity_segmentation.ipynb`      | Tests whether speed can cut a demonstration out of a recording now that the walking has gone.                            |
| -     | `object_detection.ipynb`           | September record. Why detection was abandoned for segmentation. Superseded, kept as evidence.                            |
| -     | `stereo_depth.ipynb`               | September record. Where the rectification and the prompting experiments were worked out. Superseded by notebook 3.       |

The filenames carry no numbers, so the order column is what tells you how to read them. The five
numbered notebooks all run on the October recordings and none depends on another, so any of them
can be run on its own.

The two unnumbered ones are the September development record. They still read
`pouring_scooping_1` and each opens with a note saying what replaced it. `stereo_depth` would
recreate the September deliverables in `outputs/` if you ran it, which is why those files were
removed rather than left to be confused with the current ones.

Cell outputs are committed on purpose. They are the record of what was actually observed and that
is worth more than a clean diff. `object_detection` guards its expensive propagation cell behind
`FORCE_PROPAGATION`, so it skips the work once the cached centroids exist.

That decision has a price worth knowing about. `object_detection` carries about 20 MB of embedded
images and `stereo_depth` about 9 MB, so git stores a fresh full copy of both every time a rerun gets
committed. One rerun took the history from 27 MB to 96 MB before a repack brought it back to 34 MB. Committing every rerun would push the
repository towards a gigabyte fairly quickly, so it is better to commit a rerun when the outputs
have actually changed in a way that matters.

## Things that already went wrong

These are written down so that nobody repeats them.

- Ultralytics expects BGR when you hand it a numpy array. The VRS gives RGB. Feeding it RGB ran
  every detection on swapped channels. Because the display swapped them back again, the whole
  thing looked self consistent while being wrong.
- `inspect.signature` fails on `projectaria_tools` functions because they are pybind11 bindings.
  Read `.__doc__` instead.
- The high frequency pose accessor is `get_vio_high_freq_data_by_index`. The name shortens
  `frequency` down to `freq`, so the spelling you would expect fails with an attribute error. When
  you only want a stream's rate, `get_num_data` together with `get_first_time_ns` and
  `get_last_time_ns` gives it without reading a single record.
- Save figures before calling `plt.show()`. Calling show first closes the figure, so a savefig
  afterwards writes a blank white image.
- Do not install `ultralytics[export]`. It drags in TensorFlow, CoreML and OpenVINO, downgrades
  numpy to 1.26.4 then breaks rerun-sdk.
- Never run `aria_gen2 recording delete-all`. The glasses are shared lab equipment. Delete one at
  a time with `-u <uuid>`.
- Never run `aria_gen2 auth pair` on a laptop that is already paired. It overwrites the stored
  certificate with a new one the glasses have never been told to trust, so everything afterwards
  fails with `asio.ssl error`. Nothing on the laptop can undo it. The glasses stay unusable until
  somebody with the Companion App approves the replacement. Run `aria_gen2 auth check` to confirm
  an existing pairing instead.
- Look at a contact sheet before picking a frame to work on. Several hours went into analysing
  moments where the wearer happened to be looking across the room.

## Layout

Everything this project needs now sits inside the repository. Git takes only the part of it that
belongs in git.

```
notebooks/        the six notebooks, with their cell outputs kept
outputs/          the deliverables, which are the trajectories, the clouds and the figures
reports/          the weekly progress reports
docs/             the runbook for working the glasses plus the recordings manifest
tools/            check_recordings.py validates a recording and builds the manifest,
                  render_object_cloud.py redraws the point cloud figure from the npz
requirements.txt
recordings/       the .vrs files, 5.1 GB, ignored
models/           the YOLO and SAM weights, 431 MB, ignored
cache/            exported frames, the mp4 and cached centroids, 489 MB, ignored
reference/        papers and the dataset manifest, the papers ignored
vendor/           Meta's unmodified client SDK samples, 488 KB, ignored
```

Every notebook works the repository out from its own location then reads the folders above, so you
can rename this repository or move it anywhere without breaking a single path.

## What git takes and what it leaves

The working copy runs to about 6.1 GB while the git history is 34 MB. The gap between those two
numbers is the whole arrangement, so it is worth saying plainly why the data is safe to keep here.

GitHub refuses any single file over 100 MB. Seven files here are over that limit and the largest is
a 925 MB recording, so a push carrying them would fail rather than quietly succeed. None of them
ever gets far enough to be refused, because `.gitignore` excludes `recordings/`, `models/`,
`cache/`, `vendor/` along with the pdf files inside `reference/`. Git does not list those, will not
stage them and cannot push them.

Each exclusion stands on its own merits. The recordings are the raw data and they are far too large
for git. The weights download again from Ultralytics in a single line. The cache is derived, so
`object_detection` rebuilds the exported frames and the mp4 from the recording whenever it finds
them missing. The vendored samples ship with the client SDK and were never edited here. The two papers
are public downloads. The 104 KB dataset manifest sitting beside them is versioned, because it
records which sequences we were looking at.

One consequence follows from all of this. The data is ignored rather than absent, which makes it
precisely what `git clean -x` is built to delete. Never run that command in here. The weights and
the cache would come back on their own. The 1.9 GB of recordings would not.

A fresh clone therefore arrives with the code and the deliverables and none of the data. Every
notebook except `device_calibration` checks that `recordings` and `models` exist then stops with a
clear message if either one is missing, which beats quietly writing output into the wrong place.

## Environment

The notebooks were run under Python 3.12.14 on macOS with no GPU, in a virtual environment that
lives outside the repository at `~/projectaria_gen2_python_env`. The versions in
`requirements.txt` were read out of that environment rather than chosen, so every pin is a version
that has genuinely worked.

```
python3 -m venv <somewhere outside the repository>
source <that>/bin/activate
pip install -r requirements.txt
cd notebooks && jupyter notebook
```

SAM 2 propagation over 136 frames takes several minutes on CPU.

## What is still open

The prompting question needs an answer before more tuning is worth doing, because the hand and the
gaze identify different objects and the choice depends on what the system is for.

The `vio_high_frequency` stream runs at 794.1 Hz against video at 30 fps. Using it would remove the
50 ms gap that the 10 Hz stream leaves between a pose and a frame. It also reports the device pose
directly without needing the chaining step, so it is the cheapest real improvement available.

Depth noise smears each cloud along the viewing direction, which is why the object measures 9.4 cm
deep against 4.5 cm wide. Reducing it would need either filtering across neighbouring pixels or
averaging across frames. This is the same effect that produced the bad left hand reading.

Tracking holds for about 100 frames then slides onto a nearby object while its confidence stays at
1.00, so it never reports its own failure. A longer sequence needs either re-prompting or an
independent check that the mask still sits near the hand.

Three gaps sit inside the pipeline itself. The depth window that proves no tabletop leaked into the
mask exists only as a check on one frame and it is never applied inside the 100 frame loop, so
leakage on any of the other 99 frames would go unreported. That filter has also never had to reject
anything, so its 6 cm value is untested. The loop seeds each frame's search from the previous
answer with no reset, so one bad centre would steer the next one.

Only one object is handled at a time. Several objects would mean one prompt and one track each,
which SAM supports and which has not been built.

The speed based segmentation is half fixed. `activity_segmentation.ipynb` is where that was
settled. On the September recording the method found thirteen stretches of activity covering
thirty percent of the file, most of them outside the task, because the fastest thing in that
recording was the wearer walking. On the October recordings the opening quiet period is respected
in twelve out of twelve and the number of stretches collapses to a median of two, with nothing
about the method changed. Only the data did.

What did not survive is the threshold. 0.15 m/s was chosen by eye on a recording dominated by
walking. Bench manipulation is slower than that, so most of the task now falls underneath the
line and the active fractions come out around a tenth when they ought to be nearer two thirds.
Sweeping it down to 0.04 m/s only reaches about half. So a fixed global threshold is the wrong
shape of answer. Either it scales to each recording, for eg. a percentile of that recording's own
speeds. The alternative is detecting the moment a hand closes on an object, which is the better
signal anyway because it says which object a demonstration is about rather than only when something
moved.

HOT3D has not been looked at yet. It carries ground truth object poses along with rendered masks
across 33 objects, which is what would let the prompting window be measured rather than judged by
eye.

The gaze driven interface, where a person looks at an object and a robot fetches it, has not been
started. It is the second half of the project. It shares the hardware and very little else.
