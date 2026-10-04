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
        self.timeouts = self.lures = 0
        self.stop_reason = None

    def stop(self, reason="Stopped by user."):
        if self.stop_reason is None:
            self.stop_reason = reason
        self.stop_event.set()

    def cancelled(self):
        if self.deadline is not None and self.clock() >= self.deadline:
            self.stop("Scheduled run time reached.")
        return self.stop_event.is_set()

    def wait(self, seconds):
        end = self.clock() + seconds
        if self.deadline is not None:
            end = min(end, self.deadline)
        while not self.cancelled():
            remaining = end - self.clock()
            if remaining <= 0:
                return self.cancelled()
            # Windows timed waits can return slightly early. Recheck the full
            # interval so a scheduled stop cannot slip into another cast.
            self.stop_event.wait(remaining)
        return True

    def log(self, message, *, kind=None, title=None, body="", details="", current=True):
        self.emit("log", message)
        if title:
            self.emit("activity", {"kind": kind or "info", "title": title, "body": body,
                                   "details": details, "current": current})

    def press(self, key):
        if self.cancelled():
            return False
        return self.keyboard.press(key, self.cancelled, self.wait)

    def run(self):
        cfg = self.settings
        timer = None
        started = self.clock()
        failed = False
        try:
            if cfg["STOP_AUTOMATICALLY"]:
                seconds = cfg["STOP_AFTER_MINUTES"] * 60
                self.deadline = self.clock() + seconds
                timer = Timer(seconds, lambda: self.stop("Scheduled run time reached."))
                timer.daemon = True
                timer.start()
            self.emit("state", "Starting")
            self.log("▶️ Starting fishing session. Loading bite sound references…",
                     kind="start", title="Getting ready to fish", body="Loading bite sounds and preparing your session.")
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
                self.log(f"🔊 Listening on {device['name']} (all applications on this output).",
                         kind="audio", title="Audio connected", body=device['name'],
                         details="Listening to all applications playing on this output.")
                last_lure = None
                while not self.cancelled():
                    if cfg["USE_LURE"] and (last_lure is None or self.clock() - last_lure >= cfg["LURE_COOLDOWN_SECONDS"]):
                        self.emit("state", "Applying lure")
                        if not self.press(cfg["LURE_KEY"]):
                            break
                        last_lure = self.clock()
                        self.lures += 1
                        self.log(f"🪱 Using lure with {cfg['LURE_KEY'].upper()}.",
                                 kind="lure", title="Applying a lure", body=f"Sent {cfg['LURE_KEY'].upper()} to use your lure.")
                        seconds = random.uniform(*cfg["LURE_WAIT_TIME"])
                        self.log(f"⌛ Waiting {seconds:.1f}s for the lure cast to finish.",
                                 kind="wait", title="Letting the lure finish", body=f"Fishing begins in about {seconds:.1f} seconds.")
                        if self.wait(seconds):
                            break
                    found = self.fish(backend, device, detector)
                    if self.cancelled():
                        break
                    wait_key = "WAIT_AFTER_TARGET_FOUND" if found else "WAIT_AFTER_NOT_FOUND"
                    seconds = random.uniform(*cfg[wait_key])
                    self.emit("state", "Waiting")
                    self.log(f"⌛ Next cast in {seconds:.1f}s.", kind="wait", title="Taking a short pause",
                             body=f"The next cast starts in about {seconds:.1f} seconds.")
                    if self.wait(seconds):
                        break
        except InterruptedError:
            if not self.stop_event.is_set():
                failed = True
                self.emit("error", "Audio capture was interrupted.")
        except Exception as exc:
            failed = True
            self.emit("error", str(exc) or type(exc).__name__)
        finally:
            if timer:
                timer.cancel()
            reason = "Stopped because of an error." if failed else (self.stop_reason or "Stopped.")
            elapsed = self.clock() - started
            self.log(f"⏹️ {reason}")
            self.log_summary(elapsed)
            self.emit("summary", {"elapsed": elapsed, "reason": reason, "failed": failed,
                                  "casts": self.casts, "bites": self.bites, "timeouts": self.timeouts,
                                  "interrupted": self.casts - self.bites - self.timeouts, "lures": self.lures})
            self.emit("done", None)

    def log_summary(self, elapsed):
        seconds = max(0, int(elapsed))
        self.log("📊 Session summary ────────────────────")
        self.log(f"⏱️ Run time: {seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}")
        self.log(f"🎣 Casts: {self.casts}")
        self.log(f"🐟 Bites reeled in: {self.bites} (not confirmed catches)")
        self.log(f"🔇 Casts without a bite (timed out): {self.timeouts}")
        self.log(f"⏹️ Interrupted casts: {self.casts - self.bites - self.timeouts}")
        self.log(f"🪱 Lure uses: {self.lures}")

    def fish(self, backend, device, detector):
        cfg = self.settings
        # Capture is closed between cycles so waits/lures cannot build a stale queue.
        with backend.capture(device, .1) as capture:
            stream = self.stream_factory(detector, capture.rate)
            if not self.press(cfg["ACTION_KEY"]):
                return False
            self.casts += 1
            self.emit("state", "Listening")
            self.log(f"🎣 Cast #{self.casts} · {cfg['ACTION_KEY'].upper()} · Listening for a bite…",
                     kind="cast", title=f"Cast {self.casts} · Listening for a bite",
                     body="Line is in the water. Waiting for the bite sound.",
                     details=f"Action key: {cfg['ACTION_KEY'].upper()} · Timeout: {cfg['LISTEN_DURATION']:g} seconds")
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
                    self.log(f"🐟 Bite #{self.bites} · Reeled in · score {found.score:.3f} · {found.name}",
                             kind="bite", title="Bite detected! Reeled in.",
                             body=f"{self.bites} bite{'s' if self.bites != 1 else ''} reeled in this session.",
                             details=f"Match score: {found.score:.3f} · Reference: {found.name}\n"
                                     "A reel-in key press does not confirm a catch.")
                    return True
        if not self.cancelled():
            self.timeouts += 1
            self.log("🔇 No bite detected before timeout; preparing to recast.",
                     kind="timeout", title="No bite this time", body="The cast timed out. Preparing to try again.")
        return False
