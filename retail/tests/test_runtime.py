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
