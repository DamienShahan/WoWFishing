"""Listen-only by default; --run enables cast/reel/lure keyboard actions."""
import argparse
from dataclasses import dataclass
import logging
import random
import time

from audio_io import AudioBackend, describe
from config import DEFAULT_CONFIG, load_config
from detector import SoundDetector, choose_match

LOG = logging.getLogger("fishing")


@dataclass
class SessionStats:
    cycles: int = 0
    reels: int = 0
    out_of_range: int = 0
    timeouts: int = 0
    lures: int = 0

    def recap(self, elapsed):
        hours, remaining = divmod(max(0, int(elapsed)), 3600)
        minutes, seconds = divmod(remaining, 60)
        unfinished = self.cycles - self.reels - self.out_of_range - self.timeouts
        LOG.info("📊 SESSION RECAP")
        LOG.info("⏱️ Duration: %02d:%02d:%02d", hours, minutes, seconds)
        LOG.info("🎣 Casts: %d", self.cycles)
        LOG.info("🐟 Reel-ins after bite detection: %d", self.reels)
        LOG.info("❌ Out-of-range events: %d", self.out_of_range)
        LOG.info("🔇 Timeouts without detection: %d", self.timeouts)
        LOG.info("🪱 Lure uses: %d", self.lures)
        LOG.info("⏹️ Unfinished cycles: %d", unfinished)


class Keyboard:
    def __init__(self, settings):
        import pyautogui
        from pywinauto import Desktop
        self.keys = pyautogui
        self.desktop = Desktop(backend="win32")
        self.settings = settings
        for name in ("action_key", "lure_key"):
            if settings[name] not in pyautogui.KEYBOARD_KEYS:
                raise ValueError(f"Unknown keyboard key: {settings[name]}")

    def focus(self):
        position = self.keys.position()
        self.desktop.window(title_re=self.settings["window_title_regex"]).set_focus()
        self.keys.moveTo(position.x, position.y, duration=0)

    def press(self, key, focus=True):
        if focus:
            self.focus()
        self.keys.press(key)
        LOG.info("⌨️ Pressed '%s'", key)


def log_match(match):
    label = "🐟 Bite detected" if match.event == "target" else "❌ Out of range detected"
    LOG.info("%s: %.3f >= %.3f [%s; %s] audio %.2f-%.2fs",
             label, match.score, match.threshold, match.method,
             match.template, match.start_seconds, match.end_seconds)


def process(detector, chunk, cfg, target_guard=0):
    start = time.perf_counter()
    scores = detector.process(chunk.mean(axis=1))
    elapsed = time.perf_counter() - start
    if elapsed > len(chunk) / detector.rate:
        LOG.warning("Detection took %.0fms for %.0fms of audio", elapsed * 1000, len(chunk) / detector.rate * 1000)
    for score in scores:
        LOG.debug("%s score=%.3f threshold=%.3f", score.event, score.score, score.threshold)
    scores = [m for m in scores if m.event != "target" or m.start_seconds >= target_guard]
    match = choose_match(scores, cfg["detection"]["ambiguity_margin"])
    if match is None and any(m.found for m in scores):
        LOG.info("Ambiguous event; continuing to listen")
    return match


def listen(backend, device, detector, cfg):
    LOG.info("LISTEN ONLY: fish manually; no focus changes or key presses")
    last_event_time = float("-inf")
    with backend.capture(device, cfg["audio"]["chunk_seconds"]) as capture:
        while True:
            match = process(detector, capture.read(), cfg)
            if match and match.end_seconds - last_event_time >= cfg["detection"]["cooldown_seconds"]:
                log_match(match)
                last_event_time = match.end_seconds


def run(backend, device, detector, cfg):
    auto = cfg["automation"]
    keyboard = Keyboard(auto)
    last_lure = float("-inf")
    stats = SessionStats()
    started = time.monotonic()
    LOG.info("🎣 AUTOMATION ENABLED. Ctrl+C stops; PyAutoGUI corner fail-safe remains enabled.")
    try:
        while True:
            if auto["use_lure"] and time.monotonic() - last_lure >= auto["lure_interval_seconds"]:
                LOG.info("🪱 Applying lure")
                keyboard.press(auto["lure_key"])
                stats.lures += 1
                last_lure = time.monotonic()
                time.sleep(random.uniform(*auto["lure_wait"]))
            detector.reset()
            keyboard.focus()
            result = None
            LOG.info("🎣 Cycle %d: casting", stats.cycles + 1)
            # Focus before capture; begin capture just before cast so immediate errors are heard.
            with backend.capture(device, cfg["audio"]["chunk_seconds"]) as capture:
                keyboard.press(auto["action_key"], focus=False)
                stats.cycles += 1
                deadline = time.monotonic() + auto["listen_seconds"]
                LOG.info("👂 Listening for a bite for up to %gs", auto["listen_seconds"])
                while time.monotonic() < deadline:
                    result = process(detector, capture.read(), cfg, auto["target_guard_seconds"])
                    if result:
                        log_match(result)
                        break
            if result and result.event == "target":
                LOG.info("🐟 Reeling in")
                keyboard.press(auto["action_key"])
                stats.reels += 1
                wait = auto["wait_after_target"]
            elif result and result.event == "out_of_range":
                stats.out_of_range += 1
                LOG.info("❌ Out of range: skipping reel-in")
                wait = auto["wait_after_out_of_range"]
            else:
                stats.timeouts += 1
                LOG.info("🔇 No bite before timeout")
                wait = auto["wait_after_timeout"]
            delay = random.uniform(*wait)
            LOG.info("⌛ Waiting %.2fs before the next cast", delay)
            time.sleep(delay)
    finally:
        stats.recap(time.monotonic() - started)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--run", action="store_true", help="enable keyboard automation")
    parser.add_argument("--mode", choices=("waveform", "spectral"))
    parser.add_argument("--debug", action="store_true", help="log scores below threshold too")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    # Avoid verbose dependency compilation logs when the user's score logging is enabled.
    logging.getLogger("numba").setLevel(logging.WARNING)
    cfg = load_config(args.config)
    with AudioBackend() as backend:
        device = backend.device(cfg["audio"]["device_index"])
        LOG.info("🔊 Capture: %s", describe(device))
        detector = SoundDetector(cfg, int(device["defaultSampleRate"]), args.mode)
        LOG.info("Mode: %s; %d templates; thresholds are provisional until calibrated",
                 detector.mode, len(detector.templates))
        # Warm the chosen numerical path before opening the live stream.
        import numpy as np
        detector.process(np.zeros(round(detector.rate * 0.1)))
        detector.reset()
        (run if args.run else listen)(backend, device, detector, cfg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ Stopped.")
    except Exception as exc:
        LOG.error("Stopped: %s", exc)
        raise SystemExit(1)
