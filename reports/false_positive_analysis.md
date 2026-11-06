# Quiet background false positives

Analyzed 2026-11-06 on `false-positive-handling`. All three recordings reproduce a false bite with the volume filter disabled. With the new default filter, all three are rejected while all twelve supplied real bite recordings remain detectable.

## Cause

The matcher normalizes away gain when finding spectral landmarks. It can therefore recognize a very quiet copy of a bite effect. False positives 1 and 2 match Bite 4; false positive 3 matches Bite 1. The user confirmed that all clips were captured at the same in-game volume and that these false-positive sounds are very quiet background noise.

| Recording | Reference | Highest full-reference fingerprint score before filtering | Matched-window RMS |
| --- | --- | ---: | ---: |
| false-positive1.wav | bite4.wav | 0.440 | -53.3 dBFS |
| false-positive2.wav | bite4.wav | 0.675 | -59.7 dBFS |
| false-positive3.wav | bite1.wav | 0.686 | -61.7 dBFS |

False-positive2 matches Bite 4 at approximately 1.1058x playback speed with 0.978 long-overlap waveform correlation and approximately -36.1 dB relative recorded gain. False-positive3 matches Bite 1 at approximately 0.9316x speed with 0.979 correlation and approximately -38.0 dB relative gain. These results support very quiet versions of the same recorded effects; they do not prove the identity of the in-game source or player.

False-positive1 has a 0.957 correlation over a 300 ms energetic excerpt from Bite 4, but only 0.113 over the required long overlap. Other content in the clip prevents treating its entire waveform as a simple rescaled copy. Its first-second fingerprint match is particularly quiet (about -71 dBFS RMS); its full-reference match is about -53 dBFS.

A higher fingerprint threshold alone is unsuitable: false-positive scores overlap scores from genuine bites, including noisy positive recordings. Score is an anchor coverage fraction, not a probability.

## Change

The detector now checks DC-removed RMS over the aligned candidate window after mono conversion and resampling to 16 kHz. The default floor is **-42 dBFS**. The native full-reference true bite matches range from approximately -31.6 to -22.4 dBFS; the false matches are below -53 dBFS. This leaves about 10 dB below the quietest supplied real bite and more than 11 dB above the loudest supplied false match.

Loud sound elsewhere in the rolling buffer does not raise a quiet candidate window's level. The level excludes DC offset. If a valid louder occurrence and a higher-scoring quiet copy compete for one reference, a candidate that passes all checks is preferred. The existing fingerprint threshold, playback-rate tolerance, and cooldown remain active.

In Settings:

- **Use Volume Filter** (enabled by default).
- Description: **Reduces false positives. Deactivate if you are missing bites.**
- **Minimum bite level (dBFS)** defaults to `-42`; lower values allow quieter bites. The entry is disabled when the checkbox is off, and its value is preserved.

The saved settings are `USE_BITE_LEVEL_FILTER` and `MIN_BITE_LEVEL_DBFS`. Existing settings inherit the defaults. The CLI accepts `--min-level-dbfs -50` and `--no-level-filter`; debug output reports each candidate level and identifies below-limit matches.

## Validation

| Check | Result |
| --- | --- |
| Detector, controller/settings, and GUI regression tests | 38 passed |
| Real-bite streaming cases | 48/48 detected exactly once |
| False-positive streaming cases with filter | 12/12 rejected |
| False-positive controls with filter disabled | 6/6 triggered |

Streaming covers full and one-second references, native 48 kHz recordings, and an additional 44.1 kHz / 137 ms offset case. In the latter, real bites were reduced by 6 dB and false positives amplified by 6 dB. Blocks are 100 ms with 200 ms of end padding. Regression tests additionally preserve noisy-positive and speed-variant behavior, reject reversed sounds, check matched-window/DC handling, and verify checkbox persistence and detector configuration.

Detailed results: [volume_filter_validation.json](volume_filter_validation.json). Measurements and original matcher baseline: [false_positive_analysis.json](false_positive_analysis.json).

## Limits

The floor is an absolute recording level, so different game/Windows volumes or audio setups may need adjustment. Disable **Use Volume Filter** if real bites are missed. A loud sound overlapping the candidate can lift its RMS, and this rule does not distinguish identical effects at the same level. These tests cover the supplied recordings and synthetic variations; they do not establish the live false-positive rate. Source WAVs are unchanged.
