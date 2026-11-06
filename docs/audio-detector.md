# Audio detector experiments

[Back to the user guide](../README.md) · [Source setup](development.md)

Commands below run from the project root.

This script listens to Windows output audio and prints `BITE` when it finds an
aligned landmark pattern from `sounds/target/bite1.wav`,
`sounds/target/bite2.wav`, `sounds/target/bite4.wav`, or `sounds/target/bite10.wav`
(one representative of each of the four measured groups). It never
presses keys. Source WAVs are not changed, and live audio is not saved.

The matcher now searches **0.88x through 1.12x playback speed**, allowing the
linked pitch changes found in the recordings. For example, a sound played 6%
faster is shorter and higher pitched. This does not independently model pitch
shifting at unchanged duration or time stretching at unchanged pitch.

The sound files are organized as follows:

```text
sounds/
  target/        bite1.wav, bite2.wav, bite4.wav, bite10.wav
  validation/    bite3.wav, bite5.wav, bite6.wav, bite7.wav, bite8.wav, bite9.wav,
                 bite11.wav, bite12.wav, false-positive1.wav,
                 false-positive2.wav, false-positive3.wav
```

Only the four references are loaded during normal listening. The app, listener,
and GUI self-check share the same default list. The tests and
`compare_sounds.py` use both folders; validation clips add no live processing cost.

Bite 10, Bite 11, and Bite 12 form the fourth group. Relative to Bite 10,
Bite 11 is about 1.05% faster and 1.3 dB louder; Bite 12 is about 3.15% faster
and 9.2 dB louder. Bite 10 was selected after comparing all three as references
in clean and synthetic-noise checks. See [the new bite analysis](../reports/new_bite_analysis.md).

## Run from the project root

After completing the [source setup](development.md#run-from-source):

```powershell
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
reference self-tests. The other eight recordings are useful checks of whether the
four references cover the observed playback-rate variants. Keep all twelve WAVs.

### Volume filter

**Use Volume Filter** is enabled by default in Settings. Its description is
"Reduces false positives. Deactivate if you are missing bites."
The minimum bite level defaults to **-42 dBFS RMS**. More negative values allow
quieter sounds. The saved settings are `USE_BITE_LEVEL_FILTER: true` and
`MIN_BITE_LEVEL_DBFS: -42.0`; existing settings files inherit these defaults.
Unchecking the option bypasses the level check and preserves the chosen limit.

The filter measures RMS over each aligned bite window after mono conversion,
16 kHz resampling, and DC removal. Loud audio elsewhere in the buffer cannot
raise that window's level. The fingerprint score and playback-rate matching
still apply. This is a recorded sound level, not a perceptual loudness measure.

The three supplied false-positive recordings trigger the original matcher:
the first two match Bite 4 and the third matches Bite 1. False positives 2 and 3
have approximately 0.98 waveform correlation with those references after speed
correction, but are approximately 36-38 dB quieter. With the same game volume
used for all recordings, the level filter distinguishes these quiet background
copies. The real bite recordings measure about -32 to -22 dBFS RMS in their
matched windows; the false matches are below -53 dBFS at full reference length.
See [the false-positive analysis](../reports/false_positive_analysis.md).

For a quiet game or different audio setup, lower the limit or deactivate
**Use Volume Filter** if real bites are missed. This absolute limit cannot
automatically adapt to changes in game or Windows volume. A loud overlapping
sound inside the matched window can also raise its RMS; this is not a universal
rejection of other players' sounds.

The CLI exposes both controls:

```powershell
.\.venv\Scripts\python.exe listen.py --file sounds\validation\false-positive2.wav --debug
.\.venv\Scripts\python.exe listen.py --min-level-dbfs -50 --debug
.\.venv\Scripts\python.exe listen.py --no-level-filter --debug
```

Debug output shows the candidate's `level=...dBFS` and labels candidates below
the minimum level, even when their fingerprint scores exceed the threshold.

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
The default useful reference lengths are approximately 1.53, 1.91, 2.01, and 1.73 seconds
for Bite 1, Bite 2, Bite 4, and Bite 10 respectively.
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
.\.venv\Scripts\python.exe listen.py --file sounds\validation\bite12.wav --debug
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

With the original three references, offline streaming detected each of the nine
supplied clips once, both at full reference length and with `--duration 1.0`.
The latter detected them roughly 0.9-1.1 seconds into the files. Full-length
processing p95 was approximately 29-47 ms per 100 ms input block on this machine.
These file-relative times are not measurements from the exact audible onset.
See `reports/speed_aware_validation.json` for per-file results.

With the four current references, offline streaming detected each of all twelve
clips exactly once at full reference length and with `--duration 1.0`. All three
new clips matched Bite 10. The new full-length detections occurred at 1.6-1.7 seconds
into the files, and the one-second versions at 0.9-1.0 seconds. See
`reports/four_reference_validation.json` for these results. These checks used
16 kHz mono input in 100 ms blocks and 200 ms of end padding; the historical
processing timings above have not been remeasured with four references.

The detector regression tests additionally check equal-power white noise mixed into
all twelve clips, rejection of all twelve reversed clips, synthetic playback rates
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

