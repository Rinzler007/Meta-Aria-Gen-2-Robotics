# Working the glasses

Everything here is run from a shell with the virtual environment active. The commands
are the ones that were actually used on 18 September 2026 to make the recordings in
`recordings/`, so this is a record of what worked rather than a copy of the
documentation.

Two paths changed when the project was reorganised into a single repository. `$ARIA`
now points at the repository itself, and the client SDK samples now live under
`vendor/` rather than directly in the project folder. Both are reflected below.

## Step 1: set up the shell

```bash
ARIA="/Users/harshdas/Desktop/Rinzler/Stony Brook University/Advanced Project/Meta-Aria-Gen-2-Robotics"

mkdir -p "$ARIA/recordings"

source ~/projectaria_gen2_python_env/bin/activate
```

`ARIA` only lives in the one terminal session, so set it again in any new tab.

## Step 2: install the tools

```bash
python3 -m pip install projectaria-tools==2.3.0

python3 -m aria.extract_sdk_samples --output "$ARIA/vendor"
```

The samples go into `vendor/` because they are Meta's code rather than ours, and
`.gitignore` keeps that folder out of git.

## Step 3: connect and pair

```bash
aria_gen2 device list
aria_gen2 auth pair
aria_gen2 auth check
```

## Step 4: record a demonstration

```bash
aria_gen2 recording start --profile profile10 --recording-name cup_demo_01
aria_gen2 recording stop
aria_gen2 recording list
```

Profile 10 rather than the default profile 8, because profile 10 records colour video
at 30 frames per second and that matches the hand tracking rate. On profile 8 the two
streams come out three to one and you have to reconcile them later.

## Step 5: download it

```bash
aria_gen2 recording download --help

aria_gen2 recording download -u <uuid from recording list> -o "$ARIA/recordings"
```

## Step 6: watch it back

```bash
aria_rerun_viewer --vrs "$ARIA/recordings/pouring_scooping_1_20260918_160639.vrs"
```

## Step 7: point a notebook at your own recording

```bash
python3 -m pip install -r "$ARIA/requirements.txt"

cd "$ARIA/notebooks" && jupyter notebook
```

There is nothing to edit by hand any more. The first cell of each notebook works the
repository out from its own location and then reads `recordings/`, so launching jupyter
from the `notebooks` folder is the whole of it. To use a different recording, change
the filename in the cell that sets `vrs_file_path` and leave the folder alone.

## Step 8: live streaming over the cable

```bash
aria_gen2 recording stop
aria_gen2 streaming start
```

In a second terminal:

```bash
aria_streaming_viewer --real-time --interpolate --rerun-memory-limit 4GB
```

And to finish:

```bash
aria_gen2 streaming stop
```

## Step 9: streaming into your own code

```bash
ARIA="/Users/harshdas/Desktop/Rinzler/Stony Brook University/Advanced Project/Meta-Aria-Gen-2-Robotics"

source ~/projectaria_gen2_python_env/bin/activate

python3 "$ARIA/vendor/projectaria_client_sdk_samples_gen2/device_streaming.py"
```

To save the stream to a file at the same time:

```bash
python3 "$ARIA/vendor/projectaria_client_sdk_samples_gen2/device_streaming.py" \
    --record-to-vrs "$ARIA/recordings"
```

## Step 10: wireless recording

```bash
aria_gen2 recording start --profile profile10 --recording-name untether_test
```

Unplug, roam around, then plug it back in.

```bash
aria_gen2 recording stop
aria_gen2 recording list
```

If the file is there with a size matching the full duration, then recording survives
disconnection.

## Step 11: wireless streaming over a phone hotspot

```bash
aria_gen2 device wifi scan

aria_gen2 device wifi connect --ssid "HarshiPhone" --password '<your-hotspot-password>'
```

Join the same hotspot on the Mac from the wifi menu, because both devices have to be on
the same network.

```bash
aria_gen2 streaming start --interface wifi_sta --batch-period-ms 200
```

Unplug, then in a second terminal:

```bash
aria_streaming_viewer --real-time --interpolate --rerun-memory-limit 4GB
```

Walk away from the laptop. The viewer carrying on is the proof. To capture a file at
the same time, use the step 9 script with `--record-to-vrs` rather than the viewer.
Plug it back in to stop.

```bash
aria_gen2 streaming stop
```

Keep the Personal Hotspot screen open on the phone so that it does not drop. Raise the
batch period to 800 if the stream stutters or the glasses get warm.

## Step 12: wireless streaming with no phone at all

```bash
aria_gen2 device hotspot start
aria_gen2 device hotspot status
```

Join that network on the Mac from the wifi menu.

```bash
aria_gen2 streaming start --interface wifi_sap --batch-period-ms 200
```

Unplug, view as above, then plug back in to stop.

```bash
aria_gen2 streaming stop
```

This is the real answer to the original question, since no phone is involved.

## Troubleshooting

If streaming will not start, the usual causes are an active recording, an already
running stream, a low battery or a USB problem:

```bash
aria_gen2 recording stop
aria_gen2 streaming stop
aria_gen2 device status
```

A prompt showing `dquote>` means a curly quote got into the command. Press Ctrl+C, then
turn off System Settings, Keyboard, Text Input, Edit, Use smart quotes and dashes.

Campus networks such as eduroam, SBU-GetConnected and WolfieNet-Guest will not work for
streaming. Meta's documentation states that the SDK does not support corporate,
university or public networks.

Never run `aria_gen2 recording delete-all` on shared lab glasses. Delete individually
instead:

```bash
aria_gen2 recording delete -u <uuid>
```
