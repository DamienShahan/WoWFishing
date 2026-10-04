"""Record loopback audio or trim a WAV without changing its sample rate/channels."""
import argparse
from pathlib import Path

import numpy as np
import soundfile as sf

from audio_io import AudioBackend, describe
from config import DEFAULT_CONFIG, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture_parser = commands.add_parser("capture", help="record system output without pressing any keys")
    capture_parser.add_argument("--config", default=DEFAULT_CONFIG)
    capture_parser.add_argument("--seconds", type=float, default=30)
    trim_parser = commands.add_parser("trim", help="extract a time interval from an existing WAV")
    trim_parser.add_argument("--input", required=True, type=Path)
    trim_parser.add_argument("--start", required=True, type=float)
    trim_parser.add_argument("--end", required=True, type=float)
    for subparser in (capture_parser, trim_parser):
        subparser.add_argument("--output", required=True, type=Path)
        subparser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.output.suffix.lower() != ".wav":
        parser.error("output must be a .wav file")
    if args.output.exists() and not args.overwrite:
        parser.error("output already exists; choose another name or use --overwrite")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.command == "trim":
        if args.input.resolve() == args.output.resolve():
            parser.error("input and output must be different files")
        data, rate = sf.read(args.input, dtype="float64", always_2d=True)
        if not 0 <= args.start < args.end <= len(data) / rate:
            parser.error("require 0 <= start < end <= input duration")
        data = data[round(args.start * rate):round(args.end * rate)]
        if not len(data):
            parser.error("selected interval contains no audio frames")
        sf.write(args.output, data, rate, subtype="PCM_16")
    else:
        if not np.isfinite(args.seconds) or not 0 < args.seconds <= 3600:
            parser.error("seconds must be greater than zero and at most 3600")
        cfg = load_config(args.config)
        with AudioBackend() as backend:
            device = backend.device(cfg["audio"]["device_index"])
            print("Recording", describe(device), flush=True)
            print("Fish manually. Ctrl+C keeps the audio already recorded.", flush=True)
            rate = int(device["defaultSampleRate"])
            remaining = round(rate * args.seconds)
            # Write incrementally so longer recordings do not accumulate in RAM.
            with backend.capture(device, cfg["audio"]["chunk_seconds"]) as capture:
                with sf.SoundFile(args.output, "w", samplerate=rate,
                                  channels=int(device["maxInputChannels"]), subtype="PCM_16") as output:
                    try:
                        while remaining > 0:
                            chunk = capture.read()[:remaining]
                            output.write(chunk)
                            remaining -= len(chunk)
                    except KeyboardInterrupt:
                        print("\nRecording stopped early.")
    info = sf.info(args.output)
    print(f"Saved {args.output.resolve()} ({info.duration:.3f}s, {info.samplerate} Hz, {info.channels} channels)")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as exc:
        raise SystemExit(str(exc))
