"""Compare detectors on labeled WAV clips without audio devices or keyboard input."""
import argparse
from dataclasses import asdict
import csv
import json
from pathlib import Path
import time

import numpy as np

from config import DEFAULT_CONFIG, EVENT_NAMES, load_config
from detector import SoundDetector, choose_match, read_mono


def load_manifest(path, split="all"):
    path = Path(path).resolve()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not {"path", "label", "split"}.issubset(reader.fieldnames or []):
            raise ValueError("Manifest requires path,label,split columns")
        rows = list(reader)
    seen = set()
    selected = []
    for row in rows:
        if row["label"] not in (*EVENT_NAMES, "none"):
            raise ValueError(f"Invalid label: {row['label']}")
        if row["split"] not in ("tuning", "validation"):
            raise ValueError("split must be tuning or validation")
        audio_path = (path.parent / row["path"]).resolve()
        if audio_path in seen:
            raise ValueError(f"Duplicate recording in manifest: {audio_path}")
        seen.add(audio_path)
        if not audio_path.is_file():
            raise ValueError(f"Recording not found: {audio_path}")
        if split == "all" or row["split"] == split:
            selected.append({**row, "path": audio_path})
    if not selected:
        raise ValueError("Manifest contains no clips for this split")
    return selected


def evaluate_clip(detector, audio, cfg):
    detector.reset()
    peaks = {}
    detections = []
    chunk_size = max(1, round(detector.rate * cfg["audio"]["chunk_seconds"]))
    last_detection = float("-inf")
    elapsed = []
    for offset in range(0, len(audio), chunk_size):
        started = time.perf_counter()
        matches = detector.process(audio[offset:offset + chunk_size])
        elapsed.append(time.perf_counter() - started)
        for match in matches:
            if match.event not in peaks or match.score > peaks[match.event].score:
                peaks[match.event] = match
        chosen = choose_match(matches, cfg["detection"]["ambiguity_margin"])
        if chosen and chosen.end_seconds - last_detection >= cfg["detection"]["cooldown_seconds"]:
            detections.append(asdict(chosen))
            last_detection = chosen.end_seconds
    return {
        "duration_seconds": len(audio) / detector.rate,
        "peaks": {event: asdict(match) for event, match in peaks.items()},
        "detections": detections,
        "processing_ms_p95": float(np.percentile(elapsed, 95) * 1000),
    }


def summarize(results, cfg):
    summary = {}
    for event, settings in cfg["events"].items():
        if not settings["enabled"]:
            continue
        tp = fp = fn = tn = 0
        for row in results:
            expected = row["label"] == event
            found = any(d["event"] == event for d in row["detections"])
            tp += int(expected and found)
            fp += int(not expected and found)
            fn += int(expected and not found)
            tn += int(not expected and not found)
        # Recommendations use only tuning data, never the held-out validation set.
        tuning = [r for r in results if r["split"] == "tuning"]
        positive = [r["peaks"].get(event, {}).get("score", 0) for r in tuning if r["label"] == event]
        negative = [r["peaks"].get(event, {}).get("score", 0) for r in tuning if r["label"] != event]
        suggestion = None
        note = "Need both positive and negative tuning clips."
        if positive and negative:
            if min(positive) > max(negative):
                suggestion = (min(positive) + max(negative)) / 2
                note = "Midpoint separates tuning peak scores only; re-evaluate decisions with this setting."
            else:
                note = "Tuning scores overlap; no threshold perfectly separates these clips."
        summary[event] = {
            "true_positive_clips": tp, "false_positive_clips": fp,
            "false_negative_clips": fn, "true_negative_clips": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "tuning_min_positive_score": min(positive) if positive else None,
            "tuning_max_negative_score": max(negative) if negative else None,
            "suggested_threshold": suggestion, "note": note,
        }
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--split", choices=("tuning", "validation", "all"), default="tuning")
    parser.add_argument("--mode", choices=("waveform", "spectral", "both"), default="both")
    parser.add_argument("--output", type=Path, default=Path("reports/evaluation.json"))
    args = parser.parse_args()
    cfg = load_config(args.config)
    rows = load_manifest(args.manifest, args.split)
    report = {"manifest": str(args.manifest.resolve()), "split": args.split, "modes": {}}
    modes = ("waveform", "spectral") if args.mode == "both" else (args.mode,)
    for mode in modes:
        results, detectors = [], {}
        for row in rows:
            audio, rate = read_mono(row["path"])
            if rate not in detectors:
                detectors[rate] = SoundDetector(cfg, rate, mode)
            result = evaluate_clip(detectors[rate], audio, cfg)
            result.update(path=str(row["path"]), label=row["label"], split=row["split"])
            results.append(result)
            scores = ", ".join(f"{name}={match['score']:.3f}" for name, match in result["peaks"].items())
            print(f"{mode:8s} {row['path'].name}: label={row['label']}; {scores}", flush=True)
        summary = summarize(results, cfg)
        report["modes"][mode] = {"summary": summary, "clips": results}
        for event, metrics in summary.items():
            print(f"  {event}: TP={metrics['true_positive_clips']} FP={metrics['false_positive_clips']} "
                  f"FN={metrics['false_negative_clips']} TN={metrics['true_negative_clips']}")
            print(f"    {metrics['note']} Suggested threshold: {metrics['suggested_threshold']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Report: {args.output.resolve()}")
    print("Metrics are per clip, not timestamp-verified events. Settings were not changed.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as exc:
        raise SystemExit(str(exc))
