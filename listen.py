"""Listen for bite fingerprints. Prints events; never sends keyboard input."""
import argparse
from pathlib import Path
import time

import numpy as np
import soundfile as sf

from fingerprint import FingerprintDetector, StreamDetector


def capture_backend():
    # Import capture only when a live device is requested.
    from audio_io import AudioBackend, describe
    return AudioBackend, describe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--device", type=int, help="WASAPI loopback index; default output if omitted")
    parser.add_argument("--file", type=Path, help="Scan a WAV instead of listening live")
    parser.add_argument("--references", type=Path, nargs="+", help="Default: bite1.wav, bite2.wav, bite4.wav in sounds/target/ (one per splash group)")
    parser.add_argument("--threshold", type=float, default=0.40, help="Anchor coverage, not probability (default: 0.40)")
    parser.add_argument("--speed-tolerance", type=float, default=0.12,
                        help="Fractional playback-rate range around 1.0 (default: 0.12 = +/-12%%; 0 disables)")
    parser.add_argument("--min-anchors", type=int, default=8)
    parser.add_argument("--duration", type=float, help="Use only this many seconds after each reference's quiet lead-in")
    parser.add_argument("--cooldown", type=float, default=2.0)
    parser.add_argument("--debug", action="store_true", help="Print strongest recent score every second")
    args = parser.parse_args()
    if not 0 < args.threshold <= 1 or args.min_anchors < 2 or not np.isfinite(args.cooldown) or args.cooldown < 0:
        parser.error("threshold must be in (0,1], min-anchors >= 2, cooldown >= 0")
    if args.duration is not None and (not np.isfinite(args.duration) or args.duration < 0.4):
        parser.error("duration must be at least 0.4 seconds")
    if not np.isfinite(args.speed_tolerance) or not 0 <= args.speed_tolerance <= 0.25:
        parser.error("speed-tolerance must be between 0 and 0.25")
    if args.list_devices:
        AudioBackend, describe = capture_backend()
        with AudioBackend() as backend:
            devices = list(backend.p.get_loopback_device_info_generator())
            if not devices:
                raise RuntimeError("No WASAPI loopback devices found")
            for device in devices:
                print(describe(device))
        return
    folder = Path(__file__).resolve().parent / "sounds" / "target"
    paths = args.references or [folder / f"bite{i}.wav" for i in (1, 2, 4)]
    detector = FingerprintDetector(paths, args.duration, args.threshold, args.min_anchors,
                                   args.speed_tolerance)
    print("Listen-only landmark detector. No keys are sent. Stop with Ctrl+C.")
    print(f"Provisional threshold: {args.threshold:.2f}; minimum anchors: {args.min_anchors}")
    print(f"Playback rates: {detector.speeds[0]:.2f}x to {detector.speeds[-1]:.2f}x "
          f"({len(detector.speeds)} hypotheses; linked speed/pitch changes)")
    for ref in detector.references:
        print(f"  {ref.name}: crop {ref.crop_start:.2f}s + {ref.duration:.2f}s; {len(ref.anchors)} anchors")
    count, peak, debug_peak, next_debug = 0, None, None, 1.0
    timings = []

    def process(stream, block):
        nonlocal count, peak, debug_peak, next_debug
        started = time.perf_counter()
        matches, found = stream.process(block)
        timings.append(time.perf_counter()-started)
        for match in matches:
            if peak is None or match.score > peak.score:
                peak = match
            if debug_peak is None or match.score > debug_peak.score:
                debug_peak = match
        if found:
            count += 1
            print(f"BITE #{count} at {stream.total/stream.rate:.2f}s | {found.name} "
                  f"score={found.score:.3f} anchors={found.anchors} span={found.span:.2f}s "
                  f"speed~{found.speed:.2f}x "
                  f"matched={found.start:.2f}..{found.end:.2f}s", flush=True)
        now = stream.total/stream.rate
        if args.debug and now >= next_debug:
            text = (f"{debug_peak.name} score={debug_peak.score:.3f} anchors={debug_peak.anchors} "
                    f"span={debug_peak.span:.2f}s speed~{debug_peak.speed:.2f}x" if debug_peak else "no aligned candidate")
            print(f"[{now:7.2f}s] {text} | processing={timings[-1]*1000:.0f}ms", flush=True)
            debug_peak = None
            next_debug = now+1
        if len(timings) > 1000:
            del timings[:500]

    try:
        if args.file:
            with sf.SoundFile(args.file) as recording:
                stream = StreamDetector(detector, recording.samplerate, args.cooldown)
                size = max(1, round(recording.samplerate*0.1))
                for block in recording.blocks(blocksize=size, dtype="float64", always_2d=True):
                    process(stream, block)
                # Flush only analysis lookahead, not a fabricated extra event.
                for _ in range(2):
                    process(stream, np.zeros((size, recording.channels)))
        else:
            AudioBackend, describe = capture_backend()
            with AudioBackend() as backend:
                device = backend.device(args.device)
                print("Capturing output mix: " + describe(device), flush=True)
                with backend.capture(device, 0.1) as capture:
                    stream = StreamDetector(detector, capture.rate, args.cooldown)
                    while True:
                        process(stream, capture.read())
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        print(f"Detections: {count}")
        if peak:
            print(f"Strongest score: {peak.score:.3f} ({peak.name}, {peak.anchors} anchors)")
        if timings:
            p95 = np.percentile(timings, 95)*1000
            print(f"Processing p95: {p95:.0f} ms per 100 ms block")
            if p95 > 100:
                print("Processing is slower than live input; try --duration 1.0.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc))
