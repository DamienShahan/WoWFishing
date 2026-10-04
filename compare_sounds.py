"""Compare recorded bite variants while allowing timing, gain, and playback-rate changes.

Analysis only: does not modify references or the live detector. Writes JSON and
Markdown results beside this script under reports/.
"""
import json
from pathlib import Path

import numpy as np
from scipy import signal

from fingerprint import read_audio

RATE = 8000


def change_speed(audio, speed):
    return np.interp(np.arange(0, len(audio)-1, speed), np.arange(len(audio)), audio)


def excerpt_correlation(audio, template):
    centered = template-template.mean()
    n = len(template)
    sums = np.r_[0, np.cumsum(audio)]
    squares = np.r_[0, np.cumsum(audio**2)]
    energy = squares[n:]-squares[:-n]-(sums[n:]-sums[:-n])**2/n
    numerator = signal.correlate(audio, centered, mode="valid", method="fft")
    scores = np.abs(numerator)/np.sqrt(np.maximum(energy*np.dot(centered, centered), 1e-30))
    return float(scores.max())


def aligned_correlation(x, y):
    """Best gain-invariant correlation with substantial overlap and energy coverage."""
    corr = signal.correlate(x, y, method="fft")
    lags = signal.correlation_lags(len(x), len(y))
    a, b = np.maximum(lags, 0), np.maximum(-lags, 0)
    n = np.minimum(len(x)-a, len(y)-b)
    sx, sy = np.r_[0, np.cumsum(x)], np.r_[0, np.cumsum(y)]
    ex, ey = np.r_[0, np.cumsum(x*x)], np.r_[0, np.cumsum(y*y)]
    mx, my = sx[a+n]-sx[a], sy[b+n]-sy[b]
    xx, yy = ex[a+n]-ex[a]-mx*mx/n, ey[b+n]-ey[b]-my*my/n
    scores = np.abs(corr-mx*my/n)/np.sqrt(np.maximum(xx*yy, 1e-30))
    valid = ((n >= .7*min(len(x), len(y))) & (xx >= .7*ex[-1]) & (yy >= .7*ey[-1]))
    scores[~valid] = 0
    index = int(scores.argmax())
    return {"correlation": float(np.clip(scores[index], 0, 1)),
            "overlap_seconds": float(n[index]/RATE),
            "lag_seconds": float(lags[index]/RATE)}


def main():
    root = Path(__file__).resolve().parent
    paths = sorted(
        (path for folder in ("target", "validation")
         for path in (root/"sounds"/folder).glob("bite*.wav")),
        key=lambda path: path.name,
    )
    if len(paths) < 2:
        raise SystemExit("Need at least two bite WAV files")
    # Compare a useful frequency band; remove low rumble before correlation.
    sos = signal.butter(4, [250, 3000], btype="bandpass", fs=RATE, output="sos")
    clips = [signal.sosfiltfilt(sos, signal.resample_poly(read_audio(p), 1, 2)) for p in paths]
    results = []
    for i, x in enumerate(clips):
        n = min(2400, len(x))  # 300 ms to cheaply locate promising speed ratios.
        energy = signal.convolve(x*x, np.ones(n), mode="valid", method="fft")
        start = int(energy.argmax())
        excerpt = x[start:start+n]
        for j in range(i+1, len(clips)):
            y = clips[j]
            candidates = [(excerpt_correlation(y, change_speed(excerpt, speed)), speed)
                          for speed in np.arange(.88, 1.1201, .001)]
            short_score, speed = max(candidates)
            baseline = aligned_correlation(x, y)
            verified = None
            if short_score >= .65:
                # Verify over most of the recording, not just the search excerpt.
                best = (-1, None, None)
                for refined in np.arange(speed-.0015, speed+.00151, .000025):
                    alignment = aligned_correlation(change_speed(x, refined), y)
                    if alignment["correlation"] > best[0]:
                        best = (alignment["correlation"], refined, alignment)
                _, speed, verified = best
            same = verified is not None and verified["correlation"] >= .85
            row = {"a": paths[i].name, "b": paths[j].name,
                   "unadjusted_correlation": baseline["correlation"],
                   "best_excerpt_correlation": short_score,
                   "speed_multiplier_a_to_b": float(speed),
                   "long_overlap_verification": verified,
                   "likely_same_recorded_effect": same}
            results.append(row)
            print(f"{row['a']} / {row['b']}: excerpt={short_score:.3f}; "
                  f"long={verified['correlation'] if verified else 0:.3f}; "
                  f"speed={speed:.5f}; same={same}", flush=True)
    groups = [{p.name} for p in paths]
    for pair in results:
        if pair["likely_same_recorded_effect"]:
            left = next(group for group in groups if pair["a"] in group)
            right = next(group for group in groups if pair["b"] in group)
            if left is not right:
                left.update(right)
                groups.remove(right)
    groups = [sorted(group) for group in groups]
    report = {
        "method": "8 kHz mono, 250-3000 Hz bandpass; normalized correlation with lag and speed search",
        "speed_search_range": [0.88, 1.12],
        "verification": "At least 70% of shorter duration and 70% of each clip's energy overlap",
        "limitations": "Empirical recording similarity, not proof of original game asset identities. Correlations are not probabilities.",
        "groups": groups, "pairs": results,
    }
    out = root/"reports"
    out.mkdir(exist_ok=True)
    (out/"sound_comparison.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    lines = ["# Bite sound comparison", "", "The nine recordings form three strongly supported groups." if len(paths) == 9 and len(groups) == 3 else "Groups based on verified recording similarity:", "",
             "| Group | Files |", "| --- | --- |"]
    lines += [f"| {i+1} | {', '.join(group)} |" for i, group in enumerate(groups)]
    lines += ["", "## Matching pairs after timing and speed adjustment", "",
              "Speed is the multiplier applied to file A to match file B (higher means faster and higher pitched). Correlation is not a probability.", "",
              "| A | B | Speed change | Correlation | Verified overlap |", "| --- | --- | ---: | ---: | ---: |"]
    for row in results:
        if row["likely_same_recorded_effect"]:
            match = row["long_overlap_verification"]
            lines.append(f"| {row['a']} | {row['b']} | {(row['speed_multiplier_a_to_b']-1)*100:+.2f}% | {match['correlation']:.3f} | {match['overlap_seconds']:.2f} s |")
    lines += ["", "## Interpretation", "",
              "Strong long-overlap waveform agreement after speed correction supports repeated recordings of the same underlying effects, played at different speeds/pitches. Exact source asset identities cannot be proven from these recordings alone.", "",
              "These groups motivated the playback-rate-aware detector update. The original fixed-rate matcher could miss variants when reduced to one reference per group. Keep all recordings for validation; consult README.md for the current detector defaults. This comparison script does not change WAVs or live-detector settings.", "",
              "## Method", "", report["method"]+". Search a 300 ms energetic excerpt over speed ratios 0.88-1.12, then refine strong candidates over a long overlap. "+report["verification"]+". Group only verified correlations >= 0.85. All pair results are in sound_comparison.json."]
    (out/"sound_comparison.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print("Groups:", groups)
    print("Report:", out/"sound_comparison.md")


if __name__ == "__main__":
    main()
