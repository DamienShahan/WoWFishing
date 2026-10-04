# Bite sound comparison

The nine recordings form three strongly supported groups.

| Group | Files |
| --- | --- |
| 1 | bite1.wav, bite5.wav, bite9.wav |
| 2 | bite2.wav, bite3.wav, bite6.wav, bite8.wav |
| 3 | bite4.wav, bite7.wav |

## Matching pairs after timing and speed adjustment

Speed is the multiplier applied to file A to match file B (higher means faster and higher pitched). Correlation is not a probability.

| A | B | Speed change | Correlation | Verified overlap |
| --- | --- | ---: | ---: | ---: |
| bite1.wav | bite5.wav | -1.34% | 0.976 | 1.73 s |
| bite1.wav | bite9.wav | +0.67% | 0.980 | 1.62 s |
| bite2.wav | bite3.wav | -2.23% | 0.983 | 1.96 s |
| bite2.wav | bite6.wav | -3.75% | 0.973 | 1.99 s |
| bite2.wav | bite8.wav | +5.99% | 0.977 | 1.82 s |
| bite3.wav | bite6.wav | -1.55% | 0.961 | 1.96 s |
| bite3.wav | bite8.wav | +8.40% | 0.979 | 1.80 s |
| bite4.wav | bite7.wav | +6.66% | 0.977 | 1.86 s |
| bite5.wav | bite9.wav | +2.05% | 0.982 | 1.58 s |
| bite6.wav | bite8.wav | +10.11% | 0.964 | 1.82 s |

## Interpretation

Strong long-overlap waveform agreement after speed correction supports repeated recordings of the same underlying effects, played at different speeds/pitches. Exact source asset identities cannot be proven from these recordings alone.

These groups motivated the playback-rate-aware detector update. The original fixed-rate matcher could miss variants when reduced to one reference per group. Keep all recordings for validation; consult README.md for the current detector defaults. This comparison script does not change WAVs or live-detector settings.

## Method

8 kHz mono, 250-3000 Hz bandpass; normalized correlation with lag and speed search. Search a 300 ms energetic excerpt over speed ratios 0.88-1.12, then refine strong candidates over a long overlap. At least 70% of shorter duration and 70% of each clip's energy overlap. Group only verified correlations >= 0.85. All pair results are in sound_comparison.json.
