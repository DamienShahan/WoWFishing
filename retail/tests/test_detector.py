from pathlib import Path
import tempfile
import unittest

import numpy as np
import soundfile as sf
import yaml

from config import DEFAULT_CONFIG, load_config
from detector import Match, SoundDetector, SpectralFrontend, choose_match, local_correlation
from evaluate import load_manifest, summarize


class CorrelationTests(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(32)
        self.target = self.rng.normal(0, 0.1, 800)

    def test_noise_elsewhere_does_not_change_match(self):
        audio = np.zeros(3000)
        audio[100:900] = self.target
        before = local_correlation(audio, self.target)[100]
        audio[1800:] = self.rng.normal(0, 0.8, 1200)
        after = local_correlation(audio, self.target)[100]
        self.assertAlmostEqual(before, 1, places=10)
        self.assertAlmostEqual(before, after, places=10)

    def test_gain_dc_offset_and_polarity(self):
        for gain in (0.1, 4, -2):
            score = local_correlation(gain * self.target + 0.3, self.target)[0]
            self.assertAlmostEqual(score, 1, places=10)

    def test_overlap_noise_and_score_bounds(self):
        mixed = self.target + self.rng.normal(0, 0.03, len(self.target))
        scores = local_correlation(mixed, self.target)
        self.assertGreater(scores[0], 0.9)
        self.assertLessEqual(scores[0], 1)

    def test_silence_constant_and_too_short(self):
        for value in (0, 0.5):
            self.assertTrue(np.all(local_correlation(np.full(2000, value), self.target) == 0))
        self.assertEqual(len(local_correlation(np.zeros(10), self.target)), 0)
        self.assertTrue(np.all(local_correlation(self.target, np.ones(30)) == 0))

    def test_sub_floor_signal_is_rejected(self):
        self.assertEqual(local_correlation(self.target * 1e-8, self.target)[0], 0)


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.rate = 8000
        self.cfg = load_config()
        self.cfg["config_dir"] = self.root
        self.cfg["events"]["out_of_range"]["enabled"] = False
        self.cfg["events"]["target"]["templates"] = "*.wav"
        rng = np.random.default_rng(12)
        self.target = rng.normal(0, 0.15, 2400) * np.hanning(2400)
        sf.write(self.root / "a.wav", self.target, self.rate, subtype="FLOAT")

    def test_split_reference_and_no_stale_matches(self):
        detector = SoundDetector(self.cfg, self.rate)
        audio = np.concatenate((np.zeros(733), self.target, np.zeros(5000)))
        matches = []
        for offset in range(0, len(audio), 800):
            matches.extend(detector.process(audio[offset:offset + 800]))
        passing = [m for m in matches if m.found]
        self.assertEqual(len(passing), 1)
        self.assertAlmostEqual(passing[0].start_seconds, 733 / self.rate)
        self.assertGreater(passing[0].score, 0.999)
        detector.reset()
        self.assertFalse(any(m.found for m in detector.process(np.zeros(4000))))

    def test_multiple_templates(self):
        second = np.random.default_rng(13).normal(0, 0.15, 2000)
        sf.write(self.root / "b.wav", second, self.rate, subtype="FLOAT")
        detector = SoundDetector(self.cfg, self.rate)
        best = detector.process(np.concatenate((np.zeros(300), second)))[0]
        self.assertEqual(best.template, "b.wav")
        self.assertGreater(best.score, 0.999)

    def test_resampled_template(self):
        from scipy import signal
        detector = SoundDetector(self.cfg, 16000)
        audio = signal.resample_poly(self.target.astype(np.float32).astype(float), 2, 1)
        self.assertGreater(detector.process(audio)[0].score, 0.999)

    def test_spectral_chunking_invariant(self):
        settings = self.cfg["detection"]
        whole = SpectralFrontend(self.rate, settings)
        expected, expected_ends, _ = whole.process(self.target)
        streamed = SpectralFrontend(self.rate, settings)
        parts, ends = [], []
        for offset in range(0, len(self.target), 117):
            values, positions, _ = streamed.process(self.target[offset:offset + 117])
            parts.append(values)
            ends.append(positions)
        np.testing.assert_allclose(np.concatenate(parts, axis=1), expected, rtol=1e-10, atol=1e-10)
        np.testing.assert_array_equal(np.concatenate(ends), expected_ends)

    def test_spectral_detects_template_after_silence(self):
        detector = SoundDetector(self.cfg, self.rate, "spectral")
        audio = np.concatenate((np.zeros(800), self.target, np.zeros(1600)))
        matches = []
        for offset in range(0, len(audio), 800):
            matches.extend(detector.process(audio[offset:offset + 800]))
        self.assertGreater(max(m.score for m in matches), 0.98)
        detector.reset()
        self.assertFalse(any(m.found for m in detector.process(np.zeros(8000))))

    def test_spectral_stationary_noise_has_no_startup_match(self):
        detector = SoundDetector(self.cfg, self.rate, "spectral")
        audio = np.random.default_rng(45).normal(0, 0.003, self.rate * 4)
        matches = []
        for offset in range(0, len(audio), 800):
            matches.extend(detector.process(audio[offset:offset + 800]))
        self.assertFalse(any(m.found for m in matches))

    def test_missing_and_silent_templates_fail(self):
        sf.write(self.root / "a.wav", np.zeros(2400), self.rate)
        with self.assertRaisesRegex(ValueError, "silent"):
            SoundDetector(self.cfg, self.rate)
        self.cfg["events"]["target"]["templates"] = "missing/*.wav"
        with self.assertRaisesRegex(ValueError, "No WAV"):
            SoundDetector(self.cfg, self.rate)


class DecisionsTests(unittest.TestCase):
    def test_ambiguity_and_clear_winner(self):
        target = Match("target", "waveform", 0.8, 0.6, "a", 0, 1)
        other = Match("out_of_range", "waveform", 0.81, 0.6, "b", 0, 1)
        self.assertIsNone(choose_match([target, other]))
        strong = Match("target", "waveform", 0.99, 0.6, "a", 0, 1)
        self.assertEqual(choose_match([strong, other]), strong)

    def test_classic_threshold_is_rejected(self):
        cfg = yaml.safe_load(DEFAULT_CONFIG.read_text())
        cfg["events"]["target"]["waveform_threshold"] = 1.2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.yaml"
            path.write_text(yaml.safe_dump(cfg))
            with self.assertRaises(ValueError):
                load_config(path)

    def test_quoted_boolean_is_rejected(self):
        cfg = yaml.safe_load(DEFAULT_CONFIG.read_text())
        cfg["automation"]["use_lure"] = "false"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.yaml"
            path.write_text(yaml.safe_dump(cfg))
            with self.assertRaises(ValueError):
                load_config(path)

    def test_validation_does_not_influence_threshold_suggestion(self):
        def row(label, score, split):
            return {"label": label, "split": split, "peaks": {"target": {"score": score}}, "detections": []}
        results = [row("target", 0.9, "tuning"), row("none", 0.3, "tuning"), row("none", 1, "validation")]
        summary = summarize(results, load_config())
        self.assertAlmostEqual(summary["target"]["suggested_threshold"], 0.6)

    def test_manifest_paths_are_relative_and_duplicates_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.wav").touch()
            manifest = root / "manifest.csv"
            manifest.write_text("path,label,split\nsample.wav,target,tuning\n")
            self.assertEqual(load_manifest(manifest)[0]["path"], root / "sample.wav")
            with manifest.open("a") as handle:
                handle.write("sample.wav,target,validation\n")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
