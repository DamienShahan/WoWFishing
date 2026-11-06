# New bite sound analysis: Bite 10-12

Analyzed 2026-11-06. The new recordings form a fourth measured sound group. Bite 10 was selected and moved unchanged into `sounds/target/bite10.wav`; Bite 11 and Bite 12 remain in validation.

## Speed, pitch, and gain

A speed multiplier above 1 means A must be played faster (and higher pitched) to match B. Gain describes relative recorded amplitude after alignment.

| A | B | Playback speed change | Linked pitch change | Gain change | Aligned correlation | Overlap |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| bite10.wav | bite11.wav | +1.05% | +18.1 cents | +1.3 dB | 0.9997 | 1.69 s |
| bite10.wav | bite12.wav | +3.15% | +53.7 cents | +9.2 dB | 0.9997 | 1.63 s |
| bite11.wav | bite12.wav | +2.08% | +35.6 cents | +8.1 dB | 0.9997 | 1.67 s |

Relative to Bite 10, Bite 11 is about 1.05% faster and 1.3 dB louder; Bite 12 is about 3.15% faster and 9.2 dB louder. The gain/speed/timing model explains over 99.9% of aligned waveform variance for every pair. This strongly supports variants of one effect, with small remaining recording differences.

All three sources are 48 kHz, mono, PCM16. The existing Bite 1-9 recordings are stereo; the matcher converts recordings to mono before analysis. Different amounts of padding also affect total file duration.

| File | Duration | Peak | RMS over central 99% energy | Samples at or above 0.9999 |
| --- | ---: | ---: | ---: | ---: |
| bite10.wav | 1.7345 s | -11.08 dBFS | -31.31 dBFS | 0 |
| bite11.wav | 1.7204 s | -10.17 dBFS | -30.21 dBFS | 0 |
| bite12.wav | 1.6676 s | -2.03 dBFS | -22.24 dBFS | 0 |

No source has full-scale clipping. Gain values are recording levels; these measurements cannot identify whether a level change came from the game, output volume, distance, or capture settings.

## Comparison with existing targets

The all-pairs search over 0.88x-1.12x playback rates retained the original three groups and added the group {Bite 10, Bite 11, Bite 12}. New-versus-old excerpt correlations were below 0.19, far below the 0.65 refinement gate; the three new-new pairs verified at 0.982-0.994 in that 8 kHz comparison. See [sound_comparison.md](sound_comparison.md) and [sound_comparison.json](sound_comparison.json) for all pairs.

## Reference selection

Each candidate was tested against each of the three new recordings with equal-RMS Gaussian white noise (0 dB SNR), eight fixed random seeds, and a non-grid-aligned 5973-sample leading offset. The detector used its existing threshold of 0.40 and +/-12% playback-rate search.

| Candidate reference | Accepted noisy clips | Lowest score | Median score |
| --- | ---: | ---: | ---: |
| bite10.wav | 24/24 | 0.413 | 0.465 |
| bite11.wav | 23/24 | 0.386 | 0.474 |
| bite12.wav | 24/24 | 0.408 | 0.483 |

Bite 10 passed all 24 noise cases and provided the highest minimum score. Bite 11 is the middle-speed variant but missed one noisy Bite 10 case. Bite 12 also passed every case, with a slightly lower minimum score. The small score differences do not prove universal superiority; Bite 10 is a tested representative within this sample. Full candidate results are in [new_bite_candidate_validation.json](new_bite_candidate_validation.json).

The app, CLI listener, and GUI self-check now share the references Bite 1, Bite 2, Bite 4, and Bite 10. Original WAV samples were preserved; the move was checked with SHA-256.

Offline streaming with the four references detected all twelve recordings exactly once, both at full reference length and with one-second references (24/24 cases). The new three recordings all matched Bite 10. See [four_reference_validation.json](four_reference_validation.json). The 25 detector, controller, and settings tests also passed, including clean/noisy recognition of all twelve clips and rejection of all twelve reversed clips.

## Method and limits

48kHz PCM16 source inspection; 16kHz mono, 250-3000Hz bandpass; speed initialized by the 8kHz comparison, then speed and fractional timing refined by normalized correlation; least-squares scalar gain over aligned long overlap after DC removal.

Gain is relative recorded amplitude in the analysis band, not a perceptual loudness or in-game volume measurement. Speed changes include proportional pitch changes. Residual recording/background/filter differences remain. Similarity is empirical, not proof of game asset identity; correlation is not a probability. Synthetic noise checks do not establish live gameplay accuracy.

Detailed measurements and SHA-256 values: [new_bite_analysis.json](new_bite_analysis.json).
