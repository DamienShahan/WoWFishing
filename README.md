# WoWFishing

A Windows GUI for the current audio fingerprint detector, with automated casting,
reeling in, optional lure application, and a scheduled stop. The `classic/` folder
is the old implementation and is not imported or bundled by this application.

## Desktop application

For a packaged release, extract **all** of `dist/WoWFishing-Windows.zip`, then
double-click `WoWFishing.exe` inside the extracted folder. Keep `_internal`
beside the executable. Python and terminal commands are not needed by end users.

Select the WoW window and the audio output carrying the game sound. In **Settings**,
set the action key to the in-game binding that both casts and reels in (for example,
the Better Fishing action binding). The app does not configure your game bindings.
Set the lure key to your lure macro, and enable **Use lure** if desired. Configure
wait ranges, lure interval, cast timeout, and detection threshold in Settings.

**Start bot** begins casting; **Stop bot**, closing the window, or the optional
run-time limit stops it. Settings are locked during a run. The worker checks
cancellation before key presses and during waits/capture, and releases the audio
device on exit. An ongoing detector calculation must finish before cleanup.
The selected game window is brought to the foreground before each key press.
Failure to focus it, a closed window, or an audio error stops the run and appears
in Activity. PyAutoGUI's mouse-corner fail-safe is enabled.

The audio device captures its entire output mix, including other applications;
selecting a game window does not isolate that game's audio. Each cast gets a
fresh detector buffer. A bite triggers one reel-in; no detection before the cast
timeout triggers a retry. There is currently **no out-of-range sound detector**.
Detection totals count matches, not confirmed catches. Test the provisional
threshold against real gameplay; the GUI does not improve detection accuracy.

Selections and settings persist in `settings.yaml` beside the source when running
from Python. Packaged builds create `%APPDATA%/WoWFishing/settings.yaml` on first
launch so the application folder can be read-only. `gui.py --settings PATH` (or
the executable with the same option) overrides this location. Invalid settings
are reported and preserved until corrected. Sound references are bundled resources;
user settings are stored separately and survive replacing the application folder.

### Run from source

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe gui.py
```

### Build the Windows release

Use Python 3.11 or 3.12 on Windows, with a root `.venv` already created:

```powershell
.\build.ps1
```

The script creates a separate `.venv-build`, installs `requirements-build.txt`,
and runs `WoWFishing.spec`. This avoids collecting unrelated packages from a
development environment. Output: `dist/WoWFishing/WoWFishing.exe` and
`dist/WoWFishing-Windows.zip`. Only current target sounds and current code are
included. Builds are unsigned. Validate a release on another Windows computer
before distributing broadly.

### Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

Controller tests use fake audio and keyboard input; they do not send keys to WoW.
They cover cast/reel sequencing, lure scheduling, retries, cancellation, resource
cleanup, automatic stopping, settings validation, and foreground checks.

## Console bite fingerprint experiment

This script listens to Windows output audio and prints `BITE` when it finds an
aligned landmark pattern from `sounds/target/bite1.wav`,
`sounds/target/bite2.wav`, or `sounds/target/bite4.wav`
(one representative of each of the three measured groups). It never
presses keys. Source WAVs are not changed, and live audio is not saved.

The matcher now searches **0.88x through 1.12x playback speed**, allowing the
linked pitch changes found in the recordings. For example, a sound played 6%
faster is shorter and higher pitched. This does not independently model pitch
shifting at unchanged duration or time stretching at unchanged pitch.

The sound files are organized as follows:

```text
sounds/
  target/        bite1.wav, bite2.wav, bite4.wav
  validation/    bite3.wav, bite5.wav, bite6.wav, bite7.wav, bite8.wav, bite9.wav
```

Only the three references are loaded during normal listening. The tests and
`compare_sounds.py` use both folders; validation clips add no live processing cost.

## Run from the project root

The existing root `.venv` already has the required dependencies:

```powershell
cd S:\Programming\Projects\WoWFishingBot
.\.venv\Scripts\python.exe listen.py --debug
```

Play/fish manually with the game audible. The default captures the default
Windows output device's entire mix, including other applications. Stop with
**Ctrl+C**. A score line is printed approximately once per second; `BITE` lines
mark detections. Times are seconds since capture began. The final recap shows
the detection count and strongest score.

If it listens to the wrong output:

```powershell
.\.venv\Scripts\python.exe listen.py --list-devices
.\.venv\Scripts\python.exe listen.py --device 12 --debug
```

Replace `12` with the loopback index for the game's output from the list. Indices
can change after reconnecting devices. Audio capture uses `audio_io.py` beside
`listen.py`, including its overflow/discontinuity checks.
It stops if no audio buffers arrive for three seconds.

## What to test first

Start with the defaults. Observe several real bites and ordinary sounds such as
casting, water, and nearby effects. Note missed bites and detections when no bite
occurred, along with the printed scores. Those observations matter more than the
reference self-tests. The other six recordings are useful checks of whether the
three references cover the observed playback-rate variants. Keep all nine WAVs.

The provisional threshold is **0.40**, raised from 0.30 because searching more
rates creates more opportunities for accidental matches. A score is the fraction of reference
anchors with matching peak-pair relationships, **not a probability**. Detection
also requires at least eight anchors and evidence spread across time. A reference
copy may score well below 1.0 because the FFT alignment, padding, peak selection,
and two-relationship requirement change which anchors receive support. The
`speed~1.06x` diagnostic is an approximate winning rate hypothesis, not a precise
speed measurement. A match can trigger as soon as sufficient evidence passes the
threshold, before the best-fitting rate is apparent.

If real bites are consistently detected, try reducing latency:

```powershell
.\.venv\Scripts\python.exe listen.py --duration 1.0 --debug
```

This uses one second after each reference's automatically trimmed quiet lead-in.
The default useful reference lengths are approximately 1.53, 1.91, and 2.01 seconds.
Full-reference detection waits roughly that long, plus the reference lead-in and
capture/analysis delay, adjusted for the matched playback speed. `--duration 0.75` is another experiment, with potentially
less distinctive evidence. Shortening the reference changes its score distribution;
recheck both detections and false positives.

For false positives, compare results with a stricter threshold:

```powershell
.\.venv\Scripts\python.exe listen.py --threshold 0.50 --debug
```

For missed bites, inspect scores before lowering the threshold. If bite and
non-bite scores overlap, changing the threshold alone will not solve the problem.
The default two-second cooldown limits duplicate reports; it does not establish
that a match is correct. Override with `--cooldown SECONDS` if needed.

## Offline sanity checks

```powershell
.\.venv\Scripts\python.exe listen.py --file sounds\target\bite1.wav --debug
.\.venv\Scripts\python.exe listen.py --file sounds\target\bite2.wav --debug
.\.venv\Scripts\python.exe listen.py --file sounds\validation\bite8.wav --debug
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

`--file` scans faster than real time and does not open an audio device. You can
pass any gameplay WAV. `--references PATH [PATH ...]` replaces the default reference
list. Offline mode appends 200 ms of silence to flush analysis near the file end;
reported capture times can consequently extend past the file's duration.

Regression checks cover copies shifted in time, equal-power white noise, stereo
capture resampled from 44.1 kHz, chunk boundaries, duplicate suppression, shortened
references, and simple negative signals. These are implementation checks, not
evidence of generalization to unseen game sounds. The synthetic negatives do not
measure the live false-positive rate.

With the three default references, offline streaming detected each of the nine
supplied clips once, both at full reference length and with `--duration 1.0`.
The latter detected them roughly 0.9-1.1 seconds into the files. Full-length
processing p95 was approximately 29-47 ms per 100 ms input block on this machine.
These file-relative times are not measurements from the exact audible onset.
See `reports/speed_aware_validation.json` for per-file results.

The eight regression tests additionally check equal-power white noise mixed into
all nine clips, rejection of all nine reversed clips, synthetic playback rates
between search steps, and a variant missed when speed search is disabled. White
noise is not a substitute for overlapping game sounds.

## Playback-rate controls

The rate range uses fractions: `--speed-tolerance 0.12` means +/-12%. The default
grid spacing is at most one percentage point. Matching tolerates small frequency
and time differences between grid points. To compare against fixed-rate matching:

```powershell
.\.venv\Scripts\python.exe listen.py --speed-tolerance 0 --debug
```

Ranges up to `0.25` are supported, but wider ranges cost more processing and need
another check for false positives. Start with the default. Independent pitch-only
changes would require an additional search dimension and are not promised by this
prototype.

## Method

The matcher extracts sparse spectrogram peaks, pairs peaks at different time
separations, and indexes the two frequencies plus their time difference. Incoming
audio votes for reference start times using these fingerprints. Matching allows
small frequency/time quantization differences, requires multiple relationships
per supported anchor, and checks coverage across the reference. Reference landmark
frequencies are multiplied by each candidate playback rate, while their times and
durations are divided by that rate. The transformed fingerprints are indexed once
at startup; NumPy batches the live lookups and alignment votes. Thus the program
does not resample the live audio separately for every rate hypothesis. This is an
experimental Shazam-style approach, not Shazam's implementation.

## Fresh installation, if needed

Use Python 3.11 or 3.12 on Windows:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
