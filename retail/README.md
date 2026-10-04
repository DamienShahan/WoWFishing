# Retail fishing audio detector

A new implementation of the bot in `../classic/`. It listens to Windows output
audio for a fishing bite or an out-of-range alert. **Running `python fishing.py`
only listens. Add `--run` to enable casting, reeling, and optional lure keys.**

Keep your bite references in `sounds/target/` and check detection live while fishing
manually. A separate recordings folder or test collection is not required.
[required-sounds.md](required-sounds.md) describes reference preparation, and
[PLAN.md](PLAN.md) tracks implementation and validation.

## What changed

- Waveform matching uses each candidate window's own mean and energy. Loud audio
  elsewhere in the recording no longer lowers the score of an unchanged match.
- Multiple WAV references can represent different versions of each event.
- Each event has its own threshold; scores range from 0 to 1. **Do not copy the
  classic threshold of 1.2.**
- An optional spectral mode compares the evolution of frequency bands using
  streaming PCEN background normalization. It is a candidate for improved noise
  tolerance, not a guarantee that arbitrary overlapping sounds can be separated.
- Offline evaluation uses the same streaming detector as live listening.
- Ambiguous matches are rejected, silence is gated, and capture discontinuities
  stop the program with an error instead of silently corrupting the audio.

## 1. Install

Live capture and keyboard automation require Windows. Use **Python 3.11 or 3.12**.
Open PowerShell in the `retail` folder:

```powershell
cd S:\Programming\Projects\WoWFishingBot\retail
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The commands below use `python` for readability. Activate this environment with
`.\.venv\Scripts\Activate.ps1`, or replace `python` with
`.\.venv\Scripts\python.exe` in each command. Activation is optional.

## 2. Select the output device

Start the game and make sure its audio is audible, then run:

```powershell
python list_devices.py
```

In `settings.yaml`, set `audio.device_index` to the loopback device corresponding
to the game's output. Leave it as `null` to use the default Windows output loopback.
Device indices may change when devices reconnect. Capture uses the device's native
sample rate; the reference sounds are resampled once to match it.

Loopback captures the selected output mix, including other applications using
that output. Turning down unrelated music/ambience, or routing other applications
to a different output, reduces interference before detection.

## 3. Prepare reference sounds

The defaults load every `.wav` in these directories:

```text
sounds/target/         clean fishing bite references
sounds/out_of_range/   clean out-of-range alert references
```

Use your clean retail bite references, such as `bite-1.wav` and `bite-2.wav`.
Remove obsolete references from these directories once replacements are ready. Each template must be between 0.08 and 5 seconds and contain non-silent
audio. Prefer short, distinctive clips with the full useful cue and minimal padding.
A full-template detector cannot match until that much audio has arrived; long
templates increase response delay. Stereo and mono WAVs are accepted; detection
averages all channels, while the recording tool preserves them.

If you do not have an audible out-of-range alert, set
`events.out_of_range.enabled: false`. Do not leave an unrelated alert as an active
reference. See [required-sounds.md](required-sounds.md) for the exact recording list.

## 4. Check detection while fishing manually

```powershell
python fishing.py
python fishing.py --debug
```

The first command logs detected events. `--debug` also prints below-threshold
scores. Neither command focuses the game or presses keys. Stop with **Ctrl+C**.

To try spectral matching without changing the settings file:

```powershell
python fishing.py --mode spectral --debug
```

The provisional spectral thresholds need calibration. In the initial synthetic
checks, this mode detected the copied bite but missed the short legacy range alert
at its default threshold. Waveform mode detected both. See `PLAN.md` for validation
scope; neither result establishes accuracy on new retail recordings.

Listen-only mode reports at most one event per configured cooldown. It does not
apply the automation's post-cast target guard because it cannot know when you cast.
No recordings are automatically saved; use the recording tool below.

## 5. Tune using live tests

Run `python fishing.py --mode spectral --debug` while fishing manually. Compare
scores at real bites with scores from casting and background sounds. In
`settings.yaml`, `detection.mode` selects the method; `waveform_threshold` or
`spectral_threshold` under `events.target` controls only that method. Debug is
logging, not a separate detection mode or threshold.

A lower threshold may recover missed bites but also allow false triggers. Keep
both useful bite references and change one setting at a time. No saved test
recordings are required. Out-of-range detection can remain disabled.

### Optional recording and offline tools

`record.py` and `evaluate.py` remain available if a specific failure needs further
investigation. They are optional and create output folders only when requested:

```powershell
python record.py capture --seconds 30 --output captures/session.wav
python record.py trim --input captures/session.wav --start 12.3 --end 13.1 --output sounds/target/bite-03.wav
```

Replace the example times with the real cue boundaries. Capture sends no keys;
Ctrl+C keeps audio already recorded. Existing WAVs require `--overwrite` to replace.

For an optional offline comparison, create your own `captures/manifest.csv`:

```csv
path,label,split
bite-test.wav,target,tuning
background-test.wav,none,tuning
```

Paths are relative to the manifest. Labels are `target`, `out_of_range`, or `none`;
splits are `tuning` or `validation`. Use real files and separate examples from those
used as references. Keep clips from the same session in the same split.

```powershell
python evaluate.py --manifest captures/manifest.csv --split tuning --mode both --output reports/tuning.json
```

Reports contain peak scores, detections, processing times, and clip-level metrics.
These do not verify every bite's timing. Threshold suggestions use tuning data
only and never change your settings automatically.

## 6. Enable automatic fishing

Configure the game so `automation.action_key` performs both casting and interacting
with the bobber/reeling. This project does not install an addon or configure game
bindings. Verify the chosen binding works manually in your retail setup first.

Ensure `automation.window_title_regex` matches the game window. The defaults use
the title `World of Warcraft` and action key `k`.

```powershell
python fishing.py --run
```

Each cycle:

1. Apply the optional lure when due and wait for it to finish.
2. Focus the game, open capture, and press the action key to cast.
3. Listen for up to `automation.listen_seconds`.
4. On a target match, close capture, focus the game, and press the action key to reel.
5. On an out-of-range match, end the cycle without pressing the reel key.
6. On timeout, end the cycle without pressing the reel key.
7. Wait a random interval from the corresponding configured range and repeat.

`target_guard_seconds` ignores target matches whose **start** falls too close to
the beginning of capture/cast. It helps avoid early cast effects, but is not a
substitute for negative examples. Out-of-range detection remains active immediately.
If both event types match with similar strength in one update, the program keeps
listening instead of guessing.

Set `use_lure: true` only after binding a working retail lure action to `lure_key`.
It runs immediately at the first cycle and subsequently when the interval has
elapsed, at the next cycle boundary. No classic item-specific macro is assumed.

Run output marks casting (🎣), listening (👂), bite detection/reeling (🐟),
waiting (⌛), lure use (🪱), and timeouts (🔇) with emojis.

**Ctrl+C stops the program and prints a session recap:** elapsed time, casts,
reel-ins after bite detection, out-of-range events, timeouts, lure uses, and
unfinished cycles. Errors during a run also print the recap before exiting.
Reel-ins count successfully sent reel keys; they do not verify fish actually looted.
Stopping mid-cast leaves an unfinished cycle, not a timeout or successful reel.

PyAutoGUI's corner fail-safe remains enabled for
keyboard/mouse actions. Automation brings the game to the foreground when casting,
reeling, or applying a lure; it can interrupt work in another application.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| No loopback audio | Confirm game output, rerun device listing, and ensure audio is playing. Capture stops after a three-second gap in delivered data. |
| Reference not found | Check the enabled event's glob. Template paths are relative to `settings.yaml`. |
| Never detects | Use `--debug`; check recordings and thresholds, reference length, and absolute `min_rms` gate. |
| Detects casting or other effects | Note the live score for the confusing sound; replace poor references and retune rather than only lowering thresholds. |
| Spectral mode performs worse | Use waveform mode; PCEN is sensitive to reference quality and background context. No method can guarantee detection under loud masking sounds. |
| Processing warning or queue overflow | Reduce the number/length of templates or use waveform mode. A full queue stops capture rather than processing delayed audio indefinitely. |
| Window/key error | Check the title expression and binding; run with compatible game/script privileges. |
| Stereo reference seems weak | Channel averaging can cancel unusual out-of-phase audio; inspect the original recording and output processing settings. |

## Configuration and development

Use `--config path/to/settings.yaml` with the live, recording, and evaluation tools.
Unspecified config paths resolve beside the scripts. Template paths resolve beside
the selected configuration file; CLI output paths resolve from your current directory.

```powershell
python -m unittest discover -s tests -v
```

The tests run without a game, microphone, output device, or keyboard actions.

```text
retail/
  PLAN.md                 implementation and validation milestones
  required-sounds.md      recording checklist
  settings.yaml           capture, detector, and automation settings
  fishing.py              listen-only and automated modes
  detector.py             waveform and streaming spectral matching
  config.py               configuration validation
  audio_io.py             WASAPI capture and resource handling
  list_devices.py         output loopback device list
  record.py               capture and trim commands
  evaluate.py             labeled offline comparison
  sounds/                 reference templates
  tests/                  automated regressions
```

Spectral processing uses magnitude mel bands and [librosa PCEN](https://librosa.org/doc/0.11.0/generated/librosa.pcen.html)
with continuous filter state. Each candidate's per-band temporal mean is removed
before correlation. Both methods retain overlap between capture chunks and score
only newly completed candidate windows. Spectral frames advance every 10 ms by
default; live checks use 100 ms chunks. Actual response delay also includes the
template duration, processing, and window focusing.
