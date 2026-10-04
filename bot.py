"""Cancellable fishing controller using the current landmark detector."""
from pathlib import Path
import random
from threading import Event, Timer
import time

from app_settings import validate
from audio_io import AudioBackend
from fingerprint import FingerprintDetector, StreamDetector
from windows_control import Keyboard


class BotSession:
    def __init__(self, settings, window, emit, *, backend_factory=AudioBackend,
                 detector_factory=FingerprintDetector, stream_factory=StreamDetector,
                 keyboard=None, clock=time.monotonic):
        self.settings = validate(settings)
        self.emit = emit
        self.stop_event = Event()
        self.backend_factory = backend_factory
        self.detector_factory = detector_factory
        self.stream_factory = stream_factory
        self.keyboard = keyboard if keyboard is not None else Keyboard(window)
        self.clock = clock
        self.deadline = None
        self.casts = self.bites = 0

    def stop(self):
        self.stop_event.set()

    def cancelled(self):
        if self.deadline is not None and self.clock() >= self.deadline:
            self.stop()
        return self.stop_event.is_set()

    def wait(self, seconds):
        if self.cancelled():
            return True
        if self.deadline is not None:
            seconds = min(seconds, max(0, self.deadline - self.clock()))
        self.stop_event.wait(seconds)
        return self.cancelled()

    def log(self, message):
        self.emit("log", message)

    def press(self, key):
        if self.cancelled():
            return False
        return self.keyboard.press(key, self.cancelled, self.wait)

    def run(self):
        cfg = self.settings
        timer = None
        try:
            if cfg["STOP_AUTOMATICALLY"]:
                seconds = cfg["STOP_AFTER_MINUTES"] * 60
                self.deadline = self.clock() + seconds
                timer = Timer(seconds, self.stop)
                timer.daemon = True
                timer.start()
            self.emit("state", "Starting")
            self.log("Loading bite sound references…")
            folder = Path(__file__).resolve().parent / "sounds" / "target"
            detector = self.detector_factory([folder / f"bite{i}.wav" for i in (1, 2, 4)],
                                             threshold=cfg["THRESHOLD"])
            if self.cancelled():
                return
            with self.backend_factory() as backend:
                # Device indices can change after hardware reconnects. Never silently
                # capture a different named device at the old index.
                device = backend.device(cfg["OUTPUT_DEVICE_INDEX"])
                if cfg["OUTPUT_DEVICE_NAME"] and device["name"] != cfg["OUTPUT_DEVICE_NAME"]:
                    raise RuntimeError("The audio device changed. Refresh devices and select it again.")
                self.log(f"Listening on {device['name']} (all applications on this output).")
                last_lure = None
                while not self.cancelled():
                    if cfg["USE_LURE"] and (last_lure is None or self.clock() - last_lure >= cfg["LURE_COOLDOWN_SECONDS"]):
                        self.emit("state", "Applying lure")
                        if not self.press(cfg["LURE_KEY"]):
                            break
                        last_lure = self.clock()
                        self.log(f"Applied lure with {cfg['LURE_KEY'].upper()}.")
                        if self.wait(random.uniform(*cfg["LURE_WAIT_TIME"])):
                            break
                    found = self.fish(backend, device, detector)
                    if self.cancelled():
                        break
                    wait_key = "WAIT_AFTER_TARGET_FOUND" if found else "WAIT_AFTER_NOT_FOUND"
                    seconds = random.uniform(*cfg[wait_key])
                    self.emit("state", "Waiting")
                    self.log(f"Next cast in {seconds:.1f}s.")
                    if self.wait(seconds):
                        break
        except InterruptedError:
            if not self.stop_event.is_set():
                self.emit("error", "Audio capture was interrupted.")
        except Exception as exc:
            self.emit("error", str(exc) or type(exc).__name__)
        finally:
            if timer:
                timer.cancel()
            if self.deadline is not None and self.clock() >= self.deadline:
                self.log("Scheduled run time reached.")
            self.log(f"Stopped. Casts: {self.casts} · Bite detections: {self.bites}.")
            self.emit("done", None)

    def fish(self, backend, device, detector):
        cfg = self.settings
        # Capture is closed between cycles so waits/lures cannot build a stale queue.
        with backend.capture(device, .1) as capture:
            stream = self.stream_factory(detector, capture.rate)
            if not self.press(cfg["ACTION_KEY"]):
                return False
            self.casts += 1
            self.emit("state", "Listening")
            self.log(f"Cast #{self.casts} · {cfg['ACTION_KEY'].upper()} · Listening for a bite…")
            end = self.clock() + cfg["LISTEN_DURATION"]
            while not self.cancelled() and self.clock() < end:
                block = capture.read(stop_event=self.stop_event)
                if self.cancelled() or self.clock() >= end:
                    break
                _, found = stream.process(block)
                if found:
                    if not self.press(cfg["ACTION_KEY"]):
                        return False
                    self.bites += 1
                    self.log(f"Bite #{self.bites} · Reeled in · score {found.score:.3f} · {found.name}")
                    return True
        if not self.cancelled():
            self.log("No bite detected before timeout; preparing to recast.")
        return False
