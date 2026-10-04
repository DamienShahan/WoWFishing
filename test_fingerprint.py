"""Synthetic regression checks, not a measurement of live gameplay accuracy."""
from pathlib import Path
import unittest

import numpy as np
from scipy import signal

from fingerprint import FingerprintDetector, RATE, StreamDetector, read_audio

SOUNDS = Path(__file__).resolve().parent / "sounds"


def sound_path(number):
    folder = "target" if number in (1, 2, 4) else "validation"
    return SOUNDS / folder / f"bite{number}.wav"


class FingerprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = [sound_path(1), sound_path(2)]
        cls.detector = FingerprintDetector(cls.paths)

    def test_both_references_at_arbitrary_offsets_with_equal_power_noise(self):
        for path in self.paths:
            with self.subTest(path=path.name):
                audio = read_audio(path)
                noise = np.random.default_rng(17).normal(0, np.std(audio), len(audio))
                mixed = np.pad(audio+noise, (5973, 8000))
                matches = self.detector.match(mixed)
                own = next(match for match in matches if match.name == path.name)
                self.assertTrue(self.detector.accepts(own), own)
                ref = next(ref for ref in self.detector.references if ref.name == path.name)
                self.assertAlmostEqual(own.start, 5973/RATE+ref.crop_start, delta=0.05)

    def test_silence_noise_tone_and_reversed_bite_do_not_trigger(self):
        examples = {
            "silence": np.zeros(64000),
            "noise": np.random.default_rng(2).normal(0, 0.06, 64000),
            "tone": 0.1*np.sin(2*np.pi*800*np.arange(64000)/RATE),
            "reversed": np.pad(read_audio(self.paths[0])[::-1], (4000, 8000)),
        }
        for name, audio in examples.items():
            with self.subTest(name=name):
                self.assertFalse(any(self.detector.accepts(m) for m in self.detector.match(audio)))

    def test_stream_boundaries_resampling_and_one_trigger_per_event(self):
        first = read_audio(self.paths[0])
        second = read_audio(self.paths[1])
        audio = np.concatenate((np.zeros(5973), first, np.zeros(20000), second, np.zeros(16000)))
        audio = signal.resample_poly(audio, 441, 160)
        stereo = np.column_stack((audio*0.7, audio*0.9))
        stream = StreamDetector(self.detector, 44100)
        found = []
        # An awkward block size also moves the FFT frame grid relative to references.
        for start in range(0, len(stereo), 4597):
            _, match = stream.process(stereo[start:start+4597])
            if match:
                found.append(match)
            self.assertLessEqual(len(stream.buffer), stream.keep)
        self.assertEqual([match.name for match in found], ["bite1.wav", "bite2.wav"])

    def test_one_second_references_still_detect_the_original_clips(self):
        detector = FingerprintDetector(self.paths, duration=1.0)
        for path in self.paths:
            matches = detector.match(np.pad(read_audio(path), (3777, 8000)))
            self.assertTrue(any(m.name == path.name and detector.accepts(m) for m in matches))

    def test_three_references_recognize_all_nine_with_noise(self):
        detector = FingerprintDetector([sound_path(i) for i in (1, 2, 4)])
        groups = {1: 1, 2: 2, 3: 2, 4: 4, 5: 1, 6: 2, 7: 4, 8: 2, 9: 1}
        for number, representative in groups.items():
            audio = read_audio(sound_path(number))
            for noisy in (False, True):
                with self.subTest(number=number, noisy=noisy):
                    noise = (np.random.default_rng(number).normal(0, np.std(audio), len(audio))
                             if noisy else 0)
                    matches = detector.match(np.pad(audio+noise, (5973, 8000)))
                    accepted = [m for m in matches if detector.accepts(m)]
                    self.assertTrue(accepted, matches)
                    self.assertEqual(accepted[0].name, f"bite{representative}.wav")

    def test_all_reversed_recordings_are_rejected(self):
        detector = FingerprintDetector([sound_path(i) for i in (1, 2, 4)])
        for number in range(1, 10):
            with self.subTest(number=number):
                audio = read_audio(sound_path(number))
                self.assertFalse(any(detector.accepts(m) for m in
                                     detector.match(np.pad(audio[::-1], (5973, 8000)))))

    def test_off_grid_speed_changes_and_scaled_stream_duration(self):
        detector = FingerprintDetector([sound_path(4)])
        audio = read_audio(sound_path(4))
        for speed in (0.885, 0.905, 1.075, 1.115):
            with self.subTest(speed=speed):
                changed = np.interp(np.arange(0, len(audio)-1, speed), np.arange(len(audio)), audio)
                incoming = np.pad(changed, (5973, 8000))
                stream = StreamDetector(detector, RATE)
                events = []
                for start in range(0, len(incoming), 1600):
                    _, match = stream.process(incoming[start:start+1600])
                    if match:
                        events.append(match)
                self.assertEqual(len(events), 1, events)
                match = events[0]
                self.assertAlmostEqual(match.speed, speed, delta=0.04)
                self.assertAlmostEqual(match.end-match.start,
                                       detector.references[0].duration/match.speed)

    def test_rate_search_recovers_shifted_variant_that_fixed_speed_misses(self):
        audio = np.pad(read_audio(sound_path(8)), (8000, 8000))
        fixed = FingerprintDetector([sound_path(2)], speed_tolerance=0)
        aware = FingerprintDetector([sound_path(2)])
        self.assertFalse(any(fixed.accepts(m) for m in fixed.match(audio)))
        self.assertTrue(any(aware.accepts(m) for m in aware.match(audio)))


if __name__ == "__main__":
    unittest.main()
