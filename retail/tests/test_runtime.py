"""Check capture failures and action boundaries without using real devices/keys."""
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from audio_io import Capture
from config import load_config
from detector import Match
import fishing


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.backend = SimpleNamespace(api=SimpleNamespace(paAbort=2, paContinue=0, paInt16=8), p=MagicMock())
        self.device = {"defaultSampleRate": 8000, "maxInputChannels": 4, "index": 7}

    def test_multichannel_pcm_conversion(self):
        capture = Capture(self.backend, self.device, 0.1)
        pcm = np.array([[0, 32767, -32768, 1024]], dtype=np.int16)
        capture._callback(pcm.tobytes(), 1, {}, 0)
        np.testing.assert_allclose(capture.read(), pcm.astype(float) / 32768)

    def test_overflow_is_not_silently_ignored(self):
        capture = Capture(self.backend, self.device, 0.1)
        capture._callback(b"", 0, {}, 2)
        with self.assertRaisesRegex(RuntimeError, "discontinuity"):
            capture.read()

    def test_capture_closes_on_exception(self):
        stream = self.backend.p.open.return_value
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with Capture(self.backend, self.device, 0.1):
                raise RuntimeError("test failure")
        stream.stop_stream.assert_called_once()
        stream.close.assert_called_once()

    def test_queue_backlog_stops_capture(self):
        capture = Capture(self.backend, self.device, 0.1)
        for _ in range(65):
            capture._callback(b"12345678", 1, {}, 0)
        with self.assertRaisesRegex(RuntimeError, "queue overflowed"):
            capture.read()


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()
        self.cfg["automation"]["use_lure"] = False
        self.cfg["automation"]["listen_seconds"] = 23
        self.detector = MagicMock()
        self.backend = MagicMock()
        self.backend.capture.return_value.__enter__.return_value.read.return_value = np.zeros((800, 2))

    def check_cycle(self, event):
        match = Match(event, "waveform", 0.9, 0.6, "example.wav", 1, 2)
        with patch.object(fishing, "Keyboard") as keyboard_class, \
             patch.object(fishing, "process", return_value=match), \
             patch.object(fishing.time, "sleep", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                fishing.run(self.backend, {}, self.detector, self.cfg)
            return keyboard_class.return_value.press.call_args_list

    def test_target_casts_and_reels(self):
        presses = self.check_cycle("target")
        self.assertEqual(len(presses), 2)
        self.assertTrue(all(call.args[0] == self.cfg["automation"]["action_key"] for call in presses))

    def test_out_of_range_never_reels(self):
        self.assertEqual(len(self.check_cycle("out_of_range")), 1)

    def test_recap_counts_successful_reel(self):
        with self.assertLogs(fishing.LOG, level="INFO") as logs:
            self.check_cycle("target")
        output = "\n".join(logs.output)
        self.assertIn("Casts: 1", output)
        self.assertIn("Reel-ins after bite detection: 1", output)
        self.assertIn("Unfinished cycles: 0", output)
        self.assertEqual(output.count("SESSION RECAP"), 1)

    def test_recap_counts_out_of_range_without_reel(self):
        with self.assertLogs(fishing.LOG, level="INFO") as logs:
            self.check_cycle("out_of_range")
        output = "\n".join(logs.output)
        self.assertIn("Out-of-range events: 1", output)
        self.assertIn("Reel-ins after bite detection: 0", output)
        self.assertIn("Unfinished cycles: 0", output)

    def test_failed_reel_is_not_counted_as_successful(self):
        match = Match("target", "waveform", 0.9, 0.6, "example.wav", 1, 2)
        with patch.object(fishing, "Keyboard") as keyboard_class, \
             patch.object(fishing, "process", return_value=match), \
             self.assertLogs(fishing.LOG, level="INFO") as logs:
            keyboard_class.return_value.press.side_effect = [None, RuntimeError("key failed")]
            with self.assertRaisesRegex(RuntimeError, "key failed"):
                fishing.run(self.backend, {}, self.detector, self.cfg)
        output = "\n".join(logs.output)
        self.assertIn("Casts: 1", output)
        self.assertIn("Reel-ins after bite detection: 0", output)
        self.assertIn("Unfinished cycles: 1", output)

    def test_recap_on_interruption_while_listening(self):
        with patch.object(fishing, "Keyboard"), \
             patch.object(fishing, "process", side_effect=KeyboardInterrupt), \
             self.assertLogs(fishing.LOG, level="INFO") as logs:
            with self.assertRaises(KeyboardInterrupt):
                fishing.run(self.backend, {}, self.detector, self.cfg)
        output = "\n".join(logs.output)
        self.assertIn("Unfinished cycles: 1", output)
        self.assertIn("Timeouts without detection: 0", output)
        self.backend.capture.return_value.__exit__.assert_called_once()

    def test_recap_counts_timeout(self):
        with patch.object(fishing, "Keyboard"), \
             patch.object(fishing.time, "monotonic", side_effect=[0, 0, 24, 25]), \
             patch.object(fishing.time, "sleep", side_effect=KeyboardInterrupt), \
             self.assertLogs(fishing.LOG, level="INFO") as logs:
            with self.assertRaises(KeyboardInterrupt):
                fishing.run(self.backend, {}, self.detector, self.cfg)
        output = "\n".join(logs.output)
        self.assertIn("Timeouts without detection: 1", output)
        self.assertIn("Duration: 00:00:25", output)
        self.assertIn("Unfinished cycles: 0", output)

    def test_recap_before_first_cast_during_lure_wait(self):
        self.cfg["automation"]["use_lure"] = True
        with patch.object(fishing, "Keyboard"), \
             patch.object(fishing.time, "sleep", side_effect=KeyboardInterrupt), \
             self.assertLogs(fishing.LOG, level="INFO") as logs:
            with self.assertRaises(KeyboardInterrupt):
                fishing.run(self.backend, {}, self.detector, self.cfg)
        output = "\n".join(logs.output)
        self.assertIn("Casts: 0", output)
        self.assertIn("Lure uses: 1", output)
        self.assertIn("Unfinished cycles: 0", output)

    def test_listen_only_never_creates_keyboard_controller(self):
        with patch.object(fishing, "Keyboard") as keyboard_class, \
             patch.object(fishing, "process", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                fishing.listen(self.backend, {}, self.detector, self.cfg)
            keyboard_class.assert_not_called()

    def test_target_guard_does_not_suppress_range_alert(self):
        self.detector.rate = 8000
        self.detector.process.return_value = [
            Match("target", "waveform", 0.99, 0.6, "bite.wav", 0, 0.8),
            Match("out_of_range", "waveform", 0.90, 0.6, "range.wav", 0, 0.2),
        ]
        result = fishing.process(self.detector, np.zeros((800, 2)), self.cfg, target_guard=0.8)
        self.assertEqual(result.event, "out_of_range")


if __name__ == "__main__":
    unittest.main()
