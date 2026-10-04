# Required reference sounds

Only clean bite references are needed to get started. A separate recordings folder
and a large test collection are not required; check detection live while fishing.

## Bite references

- Put WAV files in `sounds/target/`, for example `bite-1.wav` and `bite-2.wav`.
  Every WAV matching the configured pattern is loaded automatically.
- Start with one clean bite. Add a few distinct examples only when they improve
  recognition of different bite sounds.
- Aim for roughly 0.5 seconds when that contains the distinctive splash. Keep more
  if needed to capture the useful sound, and trim silence and unrelated effects.
  The detector waits for a complete reference-length window before matching.
- Record output loopback at the original sample rate, preferably 44.1 or 48 kHz
  PCM16 WAV. Mono and stereo are supported. Avoid music and other effects in the
  reference, and avoid lossy conversion or heavy audio processing.
- Remove obsolete or poor references from this folder.

## Out-of-range alert

No alert recordings are needed while `events.out_of_range.enabled` is `false`.
If you enable this feature later, add a clean recording of the actual audible cue
in `sounds/out_of_range/`.

## Live testing

Run `python fishing.py --mode spectral --debug` and fish manually. Check that real
bites trigger detection and that casts, loot sounds, and ambience do not. Share
scores and approximate bite times when tuning is needed.

Record a specific confusing or missed event only if live logs are insufficient.
The optional recording and offline tools are described in [README.md](README.md).
