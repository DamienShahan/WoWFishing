# Retail audio detector plan

The previous implementation is preserved in `../classic/`. All new implementation
and documentation belong in `retail/`.

## Goal

Detect the fishing bite and out-of-range cue reliably when other audio is present,
with measurable false triggers, missed events, and runtime cost. Keep the existing
cast / listen / reel / wait flow and optional lure support.

## Implementation checklist

- [x] Build an independently testable detector with local, zero-mean normalized
  waveform correlation, silence rejection, and multiple WAV references per event.
- [x] Add optional streaming mel-spectrogram + PCEN matching; retain its noise
  estimation state between chunks and normalize each candidate window locally.
- [x] Share the detector between live listening and offline evaluation.
- [x] Add WASAPI device selection, recording, trimming, and explicit capture errors.
- [x] Add a default listen-only mode and an explicit `--run` automation mode.
- [x] Provide configuration validation, per-event/per-method thresholds, ambiguous
  event rejection, optional lure support, and clean shutdown.
- [x] Add regression tests for normalization, noise, silence, chunk boundaries,
  multiple templates, spectral matching, and configuration validation.
- [x] Provide a user guide and `required-sounds.md` recording checklist.

## Data and calibration milestones

- [x] Bootstrap with copies of the classic references, clearly labeled as legacy.
- [ ] Record clean retail examples and independent positive/negative clips as listed
   in `required-sounds.md`. Do not use test recordings as templates.
- [ ] Compare waveform and spectral modes on a tuning split. Inspect misses and false
   detections; choose separate thresholds for target and out-of-range events.
- [ ] Evaluate the selected settings on the untouched validation split.
- [ ] Check live listen-only logs, CPU timing, and response delay while fishing
   manually. Then test `--run` during an observed session.

## Decisions

- Waveform matching is the initial default. It fixes the demonstrated whole-buffer
  normalization bug. Spectral matching is available for comparison, not assumed
  superior without actual recordings.
- Scores are in [0, 1]; the classic threshold 1.2 does not carry over.
- Initial thresholds are provisional and must be calibrated.
- Capture at the device's native rate and resample references once to that rate.
  Do not independently resample live chunks, which would introduce boundary errors.
- Preserve stereo in saved recordings; average all input channels for detection.
- No trained model or source separation in the initial version. Revisit only if
  measured performance remains inadequate with representative recordings.

## Acceptance checks

- Adding sound outside a matching waveform window does not alter that window's
  normalized score. Silence and constant input produce no match.
- A reference crossing capture chunk boundaries is still detected.
- Offline evaluation invokes the same streaming detector as live capture.
- Listen-only mode never focuses the game or sends keys.
- Ambiguous target/out-of-range matches do not trigger a reel-in.
- Resource cleanup occurs on interruption and capture failure.
- No claim of retail accuracy until held-out recordings and live checks exist.

## Status

Initial implementation completed on 2026-10-04. Real-world calibration and observed
gameplay checks require the new recordings and remain a separate milestone.

Verification completed using the existing development environment:

- 25 automated tests pass, including detector math, spectral startup noise and chunk
  continuity, capture cleanup/overflow, and mocked automation action boundaries.
- CLI help, evaluation JSON generation, WAV trimming, and overwrite protection pass.
- Synthetic smoke clips at 44.1 and 48 kHz use the legacy cues mixed into low-level
  noise. Waveform mode identifies both cues and rejects the noise-only clips.
- After fixing a PCEN startup transient, spectral mode identifies the bite and
  rejects noise-only clips. It misses the short legacy range alert at the provisional
  0.85 threshold. This is one reason waveform mode remains the default; spectral
  thresholds require real calibration, separately for each event.
- In that small synthetic run, 95th-percentile processing time was about 4-6 ms per
  100 ms chunk for waveform and 1-2 ms for spectral, with two references. These
  measurements are local observations, not performance guarantees.
- Reference copies have the same SHA-256 hashes as the untouched classic WAVs.

Synthetic clips reusing templates are regression checks, not independent evidence
of retail accuracy. No live game actions or hardware capture were performed during
implementation verification.
