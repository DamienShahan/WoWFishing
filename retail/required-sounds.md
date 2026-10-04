# Recordings needed for the retail detector

The most useful data is **clean reference cues plus separate examples of when the
detector should and should not react**. Existing files copied from `classic/` are
temporary starting points, not verified retail references.

## Recording checklist

| Recording | Suggested initial amount | What to capture | Destination |
| --- | --- | --- | --- |
| Clean fishing bite/splash | 5-10 examples across any audible variants | The moment the fish bites, distinct from the cast landing and reel/loot effects | `sounds/target/` |
| Clean out-of-range alert | 3-5 examples, if used | The exact audible cue that should end a failed cast without reeling | `sounds/out_of_range/` |
| Bites in normal ambience | 10-20 independent clips | One bite with typical water, wind, and environment audio | `recordings/tuning/` and `recordings/validation/` |
| Bites with overlapping effects | 10-20 independent clips | A bite while another effect, music, speech, mount, spell, or notification is also audible | Same test folders |
| Out-of-range in normal/noisy audio | 5-10 independent clips, if used | One alert, including realistic interference | Same test folders |
| Casting without a bite | 10 clips | Cast, bobber landing, and subsequent background; stop before any bite | Same test folders; label `none` |
| Reel-in and loot effects | 5-10 clips | Retrieve/loot sounds with the preceding bite excluded | Same test folders; label `none` |
| Other splashes and nearby players | 10 clips | Similar water/splash sounds, spells, footsteps, mounts, or other players; neither of our target cues | Same test folders; label `none` |
| Background-only audio | 2-5 minutes total, divided into 5-15s clips | Water, wind, music, NPC dialogue, quiet periods; no bite or range alert | Same test folders; label `none` |
| Known failures | Every reproducible example | Missed bites or audio that caused a false trigger, including a few seconds on either side | Same test folders, with descriptive notes |

These are starting amounts, not a guarantee of statistical coverage. Prioritize
the actual overlapping sounds that currently break detection. More varied real
negative recordings are more useful than many copies of the same clean bite.

If your setup has no out-of-range sound, tell us and disable that event in settings.
Do not manufacture a voice alert unrelated to what the game/addon actually emits.
Different voices, languages, or addon alert choices require their own references.

## How to capture

1. Use the same output device and audio settings you intend to use when fishing.
2. Run `python list_devices.py` and select the appropriate device in `settings.yaml`.
3. Record the system output while fishing manually:

   ```powershell
   python record.py capture --seconds 60 --output recordings/session-01.wav
   ```

4. Listen to the recording and note the bite/alert times.
5. Extract clean reference cues, for example:

   ```powershell
   python record.py trim --input recordings/session-01.wav --start 12.3 --end 13.1 --output sounds/target/bite-01.wav
   ```

The times above are examples; replace them with the actual cue boundaries. For
reference files, keep the distinctive attack and useful decay, with minimal leading
or trailing silence. Aim for roughly 0.2-1.2 seconds when that covers the complete
cue; shorter alerts are supported down to 0.08 seconds. Avoid long clips because
the detector needs a complete reference-length window before it can match.

For **test clips**, preserve 2-3 seconds before and after the event where possible.
Clips around 5-10 seconds are convenient. Do not remove interfering sounds from
these clips: they are the problem we need to measure. Keep one event type per clip;
split bite and range-alert events into different clips.

## Audio format and consistency

- WAV, preferably original 44.1 or 48 kHz PCM16. Mono or stereo is fine; the recorder
  preserves the output channel count and sample rate.
- Record loopback directly, not speakers through a microphone.
- Keep raw recordings. Avoid MP3 conversion, denoising, heavy compression, fades,
  or normalization before handing them over.
- For clean references, reduce unrelated audio. For evaluation, include normal and
  difficult conditions at realistic volume ratios.
- Include several locations/sessions and the sound variants you actually hear.
  Also include quiet target cues if their volume changes with distance.

## Labels and separation

Use different recordings for reference templates, threshold tuning, and validation.
Do not cut a template from a clip that will later be counted as an independent test.
Reserve about a third of the **sessions** for validation and keep all excerpts from
each session in the same split. An excerpt and its longer source recording must not
land in different splits.

Copy `recordings/manifest.example.csv` to `recordings/manifest.csv` and replace the
placeholder paths with real ones:

```csv
path,label,split,notes
tuning/target-spell-01.wav,target,tuning,bite overlaps a spell; bite starts at 2.4s
tuning/cast-only-01.wav,none,tuning,cast landing with no bite
validation/target-water-02.wav,target,validation,separate session; bite starts at 3.1s
```

Paths are relative to the manifest. Labels are exactly `target`, `out_of_range`,
or `none`. A `none` recording must contain neither event. Use notes for source
session, approximate event onset, interference type, and whether the existing bot
missed it or reacted incorrectly. Timing notes help investigate reaction delay;
the initial evaluator calculates clip-level detection metrics, not annotated
event-level timing accuracy.

## What to provide

Provide the WAVs in `retail/sounds/` and `retail/recordings/`, along with the filled
manifest. Also include a short `recordings/session-notes.md` with:

- Game locale and the addon/setting that produces the out-of-range sound, if any.
- Game audio sliders/categories and selected output device.
- Which sounds overlap when detection fails.
- Whether bite sounds vary by location or between casts.
- Which sessions belong to tuning versus validation.

If recording everything at once is inconvenient, start with **3 clean bites,
5 bites with interference, and 5 confusing sounds without a bite**. That is enough
to begin debugging; collect a larger independent set before choosing final thresholds.
