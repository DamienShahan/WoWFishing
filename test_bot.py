"""Controller tests use fake capture and keyboard input; never touch the game."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app_settings import load, save, validate
from audio_io import Capture
from bot import BotSession
from windows_control import GameWindow, Keyboard


class FakeBackend:
    def __init__(self):
        self.captures = 0
        self.closed = 0
        self.terminated = False
        self.rate = 16000
        self.read_hook = lambda: None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.terminated = True

    def device(self, index):
        return {"name": "Test output"}

    def capture(self, *_):
        backend = self

        class Stream:
            rate = 16000

            def __enter__(self):
                backend.captures += 1
                return self

            def read(self, **kwargs):
                backend.read_hook()
                return [0]

            def __exit__(self, *_):
                backend.closed += 1
        return Stream()


class BotTests(unittest.TestCase):
    def session(self, **settings):
        self.backend = FakeBackend()
        self.keys = []
        self.events = []
        self.keyboard = Mock()
        self.keyboard.press.side_effect = lambda key, *_: self.keys.append(key) or True
        self.stream = Mock()
        self.stream.process.return_value = ([], SimpleNamespace(score=.6, name="bite1.wav"))
        self.stream_factory = Mock(return_value=self.stream)
        self.bot = BotSession(settings, None, lambda *event: self.events.append(event),
                              backend_factory=lambda: self.backend,
                              detector_factory=Mock(), stream_factory=self.stream_factory,
                              keyboard=self.keyboard)
        return self.bot

    def test_cast_then_reel_and_fresh_capture_for_each_cast(self):
        bot = self.session()
        waits = []

        def wait(seconds):
            waits.append(seconds)
            if len(waits) == 2:
                bot.stop()
            return bot.cancelled()
        bot.wait = wait
        bot.run()
        self.assertEqual(self.keys, ["k"] * 4)
        self.assertEqual((bot.casts, bot.bites), (2, 2))
        self.assertEqual(self.backend.captures, 2)
        self.assertEqual(self.backend.closed, 2)
        self.assertEqual(self.stream_factory.call_count, 2)
        self.assertTrue(self.backend.terminated)
        self.assertTrue(all(3 <= n <= 5 for n in waits))

    def test_lure_before_first_cast_and_on_interval(self):
        bot = self.session(USE_LURE=True, LURE_COOLDOWN_SECONDS=10)
        now = [0.]
        bot.clock = lambda: now[0]

        def wait(seconds):
            now[0] += seconds
            if bot.bites == 1:
                now[0] += 20
            if bot.bites == 2:
                bot.stop()
            return bot.cancelled()
        bot.wait = wait
        bot.run()
        self.assertEqual(self.keys, ["f5", "k", "k", "f5", "k", "k"])

    def test_stop_during_capture_prevents_reel(self):
        bot = self.session()
        self.backend.read_hook = bot.stop
        bot.run()
        self.assertEqual(self.keys, ["k"])
        self.assertEqual(bot.bites, 0)
        self.stream.process.assert_not_called()
        self.assertEqual(self.backend.closed, 1)

    def test_stop_during_matching_prevents_reel(self):
        bot = self.session()

        def process(_):
            bot.stop()
            return [], SimpleNamespace(score=.6, name="bite.wav")
        self.stream.process.side_effect = process
        bot.run()
        self.assertEqual(self.keys, ["k"])

    def test_scheduled_stop_interrupts_long_lure_wait(self):
        bot = self.session(USE_LURE=True, STOP_AUTOMATICALLY=True, STOP_AFTER_MINUTES=.01,
                           LURE_WAIT_TIME=[30, 30])
        thread = Thread(target=bot.run)
        thread.start()
        thread.join(2)
        if thread.is_alive():
            bot.stop()
            thread.join(1)
            self.fail("Scheduled stop did not interrupt wait")
        self.assertEqual(self.keys, ["f5"])
        self.assertTrue(any("Scheduled" in str(e) for e in self.events))

    def test_timeout_retries_without_reeling(self):
        bot = self.session(LISTEN_DURATION=1)
        now = [0.]
        bot.clock = lambda: now[0]
        self.backend.read_hook = lambda: now.__setitem__(0, now[0] + .6)
        self.stream.process.return_value = ([], None)

        def wait(seconds):
            self.assertTrue(.5 <= seconds <= 1.5)
            if bot.casts >= 2:
                bot.stop()
            return bot.cancelled()
        bot.wait = wait
        bot.run()
        self.assertEqual(self.keys, ["k", "k"])
        self.assertEqual(bot.bites, 0)

    def test_capture_failure_closes_resources_and_reports_error(self):
        bot = self.session()
        self.backend.read_hook = Mock(side_effect=RuntimeError("device unplugged"))
        bot.run()
        self.assertEqual(self.backend.closed, 1)
        self.assertTrue(self.backend.terminated)
        self.assertIn(("error", "device unplugged"), self.events)
        self.assertEqual(self.events[-1], ("done", None))

    def test_changed_device_never_sends_keys(self):
        bot = self.session(OUTPUT_DEVICE_INDEX=3, OUTPUT_DEVICE_NAME="Other output")
        bot.run()
        self.assertFalse(self.keys)
        self.assertTrue(any(e[0] == "error" for e in self.events))

    def test_stop_before_start_never_sends_keys(self):
        bot = self.session()
        bot.stop()
        bot.run()
        self.assertFalse(self.keys)

    def test_capture_read_can_be_cancelled_without_audio(self):
        capture = Capture(None, {"defaultSampleRate": 16000, "maxInputChannels": 1}, .1)
        event = Event()
        outcome = []

        def read():
            try:
                capture.read(stop_event=event)
            except InterruptedError:
                outcome.append("cancelled")
        thread = Thread(target=read)
        thread.start()
        time.sleep(.03)
        event.set()
        thread.join(.5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome, ["cancelled"])


class SettingsTests(unittest.TestCase):
    def test_round_trip(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.yaml"
            cfg = save(path, {"ACTION_KEY": "F2", "WAIT_AFTER_NOT_FOUND": [1, 2]})
            self.assertEqual(load(path), cfg)
            self.assertEqual(cfg["ACTION_KEY"], "f2")

    def test_invalid_settings_rejected(self):
        for values in ({"ACTION_KEY": "ctrl+k"}, {"WAIT_AFTER_NOT_FOUND": [3, 1]},
                       {"THRESHOLD": float("nan")}, {"USE_LURE": "false"},
                       {"STOP_AFTER_MINUTES": 0}, {"OUTPUT_DEVICE_INDEX": True},
                       {"WOW_TITLE_REGEX": "["}, {"UNKNOWN": 1}, {"LURE_WAIT_TIME": [-1, 2]}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate(values)

    def test_bad_file_is_not_overwritten(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.yaml"
            path.write_text("[bad", encoding="utf-8")
            with self.assertRaises(ValueError):
                load(path)
            self.assertEqual(path.read_text(), "[bad")


class KeyboardTests(unittest.TestCase):
    def test_unfocused_or_replaced_window_does_not_receive_keys(self):
        for valid, pid, foreground in ((False, 44, 123), (True, 99, 123), (True, 44, 999)):
            with self.subTest(valid=valid, pid=pid, foreground=foreground):
                gui = Mock()
                gui.IsWindow.return_value = valid
                gui.IsIconic.return_value = False
                gui.GetWindowText.return_value = "World of Warcraft"
                gui.GetForegroundWindow.return_value = foreground
                process = Mock()
                process.GetWindowThreadProcessId.return_value = (1, pid)
                keyboard = Mock()
                with patch.dict("sys.modules", {"win32gui": gui, "win32process": process, "pyautogui": keyboard}):
                    with self.assertRaises(RuntimeError):
                        Keyboard(GameWindow(123, 44, "World of Warcraft")).press("k", lambda: False, lambda _: False)
                keyboard.press.assert_not_called()


if __name__ == "__main__":
    unittest.main()
