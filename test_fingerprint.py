"""Recorded and synthetic audio regression checks, not live gameplay accuracy."""
from pathlib import Path
import unittest

import numpy as np
import soundfile as sf
from scipy import signal

from fingerprint import FingerprintDetector, RATE, StreamDetector, default_reference_paths, read_audio

SOUNDS = Path(__file__).resolve().parent / "sounds"


def sound_path(number):
    folder = "target" if (SOUNDS / "target" / f"bite{number}.wav").exists() else "validation"
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

    def test_four_references_recognize_all_twelve_with_noise(self):
        detector = FingerprintDetector(default_reference_paths())
        groups = {1: 1, 2: 2, 3: 2, 4: 4, 5: 1, 6: 2, 7: 4, 8: 2, 9: 1,
                  10: 10, 11: 10, 12: 10}
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
        detector = FingerprintDetector(default_reference_paths())
        for number in range(1, 13):
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

    def test_recorded_false_positives_are_rejected_in_native_rate_streams(self):
        for duration in (None, 1.0):
            detector = FingerprintDetector(default_reference_paths(), duration=duration)
            for number in (1, 2, 3):
                with self.subTest(duration=duration, number=number):
                    audio, rate = sf.read(SOUNDS / "validation" / f"false-positive{number}.wav",
                                          always_2d=True)
                    # Shift the recording away from the stream's FFT/block grid.
                    audio = np.pad(audio, ((round(.137*rate), round(.3*rate)), (0, 0)))
                    stream = StreamDetector(detector, rate)
                    events, candidates = [], []
                    size = round(.1*rate)
                    for start in range(0, len(audio), size):
                        matches, found = stream.process(audio[start:start+size])
                        candidates.extend(matches)
                        if found:
                            events.append(found)
                    self.assertFalse(events, events)
                    # These recordings really reach the fingerprint threshold;
                    # the level check is what rejects the strongest candidate.
                    strongest = max(candidates, key=lambda match: match.score)
                    self.assertGreaterEqual(strongest.score, detector.threshold)
                    self.assertLess(strongest.level_dbfs, detector.min_level_dbfs)

    def test_level_filter_can_be_disabled_or_adjusted_for_quiet_bites(self):
        audio = np.pad(read_audio(sound_path(1))*.01, (5973, 8000))
        for floor, accepted in ((-42.0, False), (None, True), (-70.0, True)):
            with self.subTest(floor=floor):
                detector = FingerprintDetector(default_reference_paths(), min_level_dbfs=floor)
                matches = detector.match(audio)
                self.assertEqual(any(detector.accepts(m) for m in matches), accepted, matches)

    def test_all_real_bites_remain_detectable_six_db_quieter(self):
        for duration in (None, 1.0):
            detector = FingerprintDetector(default_reference_paths(), duration=duration)
            for number in range(1, 13):
                with self.subTest(duration=duration, number=number):
                    audio = np.pad(read_audio(sound_path(number))*10**(-6/20), (5973, 8000))
                    matches = detector.match(audio)
                    self.assertTrue(any(detector.accepts(m) for m in matches), matches)

    def test_level_uses_matched_window_and_excludes_dc(self):
        detector = FingerprintDetector([sound_path(1)])
        quiet = read_audio(sound_path(1))*.1
        loud = .05*np.sin(2*np.pi*800*np.arange(16000)/RATE)
        audio = np.concatenate((loud, np.zeros(16000), quiet, np.zeros(8000)))
        for dc in (0, .02):
            with self.subTest(dc=dc):
                matches = detector.match(audio+dc)
                self.assertTrue(matches)
                self.assertFalse(any(detector.accepts(m) for m in matches), matches)
                self.assertLess(matches[0].level_dbfs, -42)

    def test_quiet_copy_does_not_hide_a_louder_noisy_bite(self):
        detector = FingerprintDetector([sound_path(1)])
        audio = read_audio(sound_path(1))
        noisy = audio + np.random.default_rng(17).normal(0, np.std(audio), len(audio))
        incoming = np.concatenate((np.zeros(5973), audio*.07, np.zeros(8000), noisy*.4,
                                   np.zeros(8000)))
        matches = detector.match(incoming)
        self.assertTrue(any(detector.accepts(m) for m in matches), matches)
        self.assertGreater(matches[0].start, (5973+len(audio))/RATE)


if __name__ == "__main__":
    unittest.main()
