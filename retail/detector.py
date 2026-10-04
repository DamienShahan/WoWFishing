"""Streaming sound matching without audio devices or keyboard dependencies."""
from dataclasses import dataclass
from glob import glob
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal


def read_mono(path, sample_rate=None):
    audio, rate = sf.read(path, dtype="float64", always_2d=True)
    if not len(audio) or not np.isfinite(audio).all():
        raise ValueError(f"Empty or non-finite audio: {path}")
    audio = audio.mean(axis=1)
    if sample_rate is not None and rate != sample_rate:
        divisor = gcd(rate, sample_rate)
        audio = signal.resample_poly(audio, sample_rate // divisor, rate // divisor)
        rate = sample_rate
    return audio, rate


def local_correlation(audio, template, min_rms=0.0001):
    """Absolute Pearson correlation at each valid offset; no global normalization."""
    audio = np.asarray(audio, dtype=np.float64)
    template = np.asarray(template, dtype=np.float64)
    size = len(template)
    if size < 2 or len(audio) < size:
        return np.empty(0)
    centered = template - template.mean()
    energy = np.dot(centered, centered)
    if energy <= 1e-20:
        return np.zeros(len(audio) - size + 1)
    sums = np.concatenate(([0.0], np.cumsum(audio)))
    squares = np.concatenate(([0.0], np.cumsum(audio * audio)))
    local_sums = sums[size:] - sums[:-size]
    local_energy = np.maximum(squares[size:] - squares[:-size] - local_sums ** 2 / size, 0)
    numerator = signal.correlate(audio, centered, mode="valid", method="fft")
    denominator = np.sqrt(local_energy * energy)
    scores = np.zeros_like(numerator)
    good = (local_energy >= size * min_rms ** 2) & (denominator > 1e-20)
    np.divide(np.abs(numerator), denominator, out=scores, where=good)
    return np.clip(scores, 0, 1)


class SpectralFrontend:
    """Causal mel/PCEN features. Frames and PCEN state survive chunk boundaries."""
    def __init__(self, rate, settings):
        import librosa
        self.librosa = librosa
        self.rate = rate
        self.hop = max(1, round(rate * settings["spectral_hop_ms"] / 1000))
        self.window = max(16, round(rate * settings["spectral_window_ms"] / 1000))
        self.bands = settings["spectral_bands"]
        self.time_constant = settings["pcen_time_constant"]
        self.mel = librosa.filters.mel(sr=rate, n_fft=self.window, n_mels=self.bands)
        self.taper = signal.windows.hann(self.window, sym=False)
        self.reset()

    def reset(self):
        self.pending = np.empty(0)
        self.offset = 0
        self.state = None

    def process(self, chunk):
        self.pending = np.concatenate((self.pending, chunk))
        if len(self.pending) < self.window:
            return np.empty((self.bands, 0)), np.empty(0, dtype=int), np.empty(0)
        frames = np.lib.stride_tricks.sliding_window_view(self.pending, self.window)[::self.hop]
        # Magnitude (not power) input and PCM scaling agree with librosa PCEN guidance.
        magnitudes = np.abs(np.fft.rfft(frames * self.taper, axis=1)).T
        mel = self.mel @ (magnitudes * 2**31)
        if self.state is None:
            # Start the smoother at the first frame's level. A zero initial state
            # would create a large artificial decay even for stationary noise.
            time_frames = self.time_constant * self.rate / self.hop
            coefficient = (np.sqrt(1 + 4 * time_frames ** 2) - 1) / (2 * time_frames ** 2)
            self.state = (1 - coefficient) * mel[:, :1]
        features, self.state = self.librosa.pcen(
            mel, sr=self.rate, hop_length=self.hop,
            time_constant=self.time_constant, zi=self.state, return_zf=True,
        )
        ends = self.offset + self.window + np.arange(len(frames)) * self.hop
        powers = np.var(frames, axis=1)
        consumed = len(frames) * self.hop
        self.pending = self.pending[consumed:].copy()
        self.offset += consumed
        return features, ends, powers


def spectral_correlation(features, template):
    """Pearson similarity after removing each band's local temporal mean."""
    width = template.shape[1]
    if width < 2 or features.shape[1] < width:
        return np.empty(0)
    centered = template - template.mean(axis=1, keepdims=True)
    energy = np.sum(centered ** 2)
    sums = np.pad(np.cumsum(features, axis=1), ((0, 0), (1, 0)))
    squares = np.pad(np.cumsum(features ** 2, axis=1), ((0, 0), (1, 0)))
    window_sums = sums[:, width:] - sums[:, :-width]
    local_energy = np.maximum(np.sum(
        squares[:, width:] - squares[:, :-width] - window_sums ** 2 / width, axis=0
    ), 0)
    numerator = signal.correlate(features, centered, mode="valid", method="fft")[0]
    denominator = np.sqrt(local_energy * energy)
    scores = np.zeros_like(numerator)
    np.divide(numerator, denominator, out=scores, where=denominator > 1e-15)
    return np.clip(scores, 0, 1)


@dataclass(frozen=True)
class Match:
    event: str
    method: str
    score: float
    threshold: float
    template: str
    start_seconds: float
    end_seconds: float

    @property
    def found(self):
        return self.score >= self.threshold

    @property
    def margin(self):
        return (self.score - self.threshold) / max(1 - self.threshold, 1e-12)


def choose_match(matches, ambiguity_margin=0.05):
    """Reject similarly strong matches belonging to different event classes."""
    passing = sorted((m for m in matches if m.found), key=lambda m: m.margin, reverse=True)
    if not passing:
        return None
    best = passing[0]
    if any(m.event != best.event and best.margin - m.margin <= ambiguity_margin for m in passing[1:]):
        return None
    return best


class SoundDetector:
    def __init__(self, cfg, sample_rate, mode=None):
        self.cfg, self.rate = cfg, sample_rate
        self.mode = mode or cfg["detection"]["mode"]
        if self.mode not in ("waveform", "spectral"):
            raise ValueError("Unknown detection mode")
        self.min_rms = cfg["audio"]["min_rms"]
        self.frontend = SpectralFrontend(sample_rate, cfg["detection"]) if self.mode == "spectral" else None
        self.templates = []
        for event, settings in cfg["events"].items():
            if not settings["enabled"]:
                continue
            pattern = str(Path(cfg["config_dir"]) / settings["templates"])
            paths = sorted(glob(pattern))
            if not paths:
                raise ValueError(f"No WAV references for {event}: {pattern}")
            for path in paths:
                audio, _ = read_mono(path, sample_rate)
                duration = len(audio) / sample_rate
                if not 0.08 <= duration <= 5:
                    raise ValueError(f"Reference must be 0.08 to 5 seconds: {path}")
                if np.std(audio) < self.min_rms:
                    raise ValueError(f"Reference is silent or below min_rms: {path}")
                representation = audio
                if self.frontend:
                    self.frontend.reset()
                    # Give the isolated cue a quiet prehistory; discard frames
                    # crossing that padding so reference timing stays unchanged.
                    padding = self.frontend.hop * max(1, round(0.5 * sample_rate / self.frontend.hop))
                    representation, ends, _ = self.frontend.process(np.concatenate((np.zeros(padding), audio)))
                    representation = representation[:, ends - self.frontend.window >= padding]
                    if representation.shape[1] < 3 or np.sum(np.var(representation, axis=1)) < 1e-15:
                        raise ValueError(f"Reference has insufficient spectral variation: {path}")
                self.templates.append((event, Path(path).name, representation, settings[self.mode + "_threshold"]))
        self.max_size = max(t[2].shape[-1] for t in self.templates)
        self.reset()

    def reset(self):
        self.total = 0
        self.audio = np.empty(0)
        if self.frontend:
            self.frontend.reset()
            self.features = np.empty((self.frontend.bands, 0))
            self.ends = np.empty(0, dtype=int)
            self.powers = np.empty(0)

    def process(self, chunk):
        chunk = np.asarray(chunk, dtype=np.float64)
        if chunk.ndim != 1 or not np.isfinite(chunk).all():
            raise ValueError("Detector requires finite, mono audio")
        if not len(chunk):
            return []
        previous_total = self.total
        self.total += len(chunk)
        results = {}
        if self.frontend:
            new_features, ends, powers = self.frontend.process(chunk)
            if not len(ends):
                return []
            self.features = np.concatenate((self.features, new_features), axis=1)
            self.ends = np.concatenate((self.ends, ends))
            self.powers = np.concatenate((self.powers, powers))
        else:
            self.audio = np.concatenate((self.audio, chunk))
        for event, name, template, threshold in self.templates:
            width = template.shape[-1]
            if self.frontend:
                scores = spectral_correlation(self.features, template)
                candidate_ends = self.ends[width - 1:]
                duration = (self.frontend.window + (width - 1) * self.frontend.hop) / self.rate
                if len(scores):
                    sums = np.concatenate(([0.0], np.cumsum(self.powers)))
                    valid_power = (sums[width:] - sums[:-width]) / width >= self.min_rms ** 2
                    scores = np.where(valid_power, scores, 0)
            else:
                scores = local_correlation(self.audio, template, self.min_rms)
                candidate_ends = self.total - len(self.audio) + np.arange(width, len(self.audio) + 1)
                duration = width / self.rate
            eligible = np.flatnonzero(candidate_ends > previous_total)
            if not len(scores) or not len(eligible):
                continue
            index = eligible[np.argmax(scores[eligible])]
            end = float(candidate_ends[index] / self.rate)
            match = Match(event, self.mode, float(scores[index]), threshold, name, max(0, end - duration), end)
            if event not in results or match.score > results[event].score:
                results[event] = match
        # Keep enough history for a reference spanning the next chunk boundary.
        if self.frontend:
            self.features = self.features[:, -self.max_size:].copy()
            self.ends = self.ends[-self.max_size:].copy()
            self.powers = self.powers[-self.max_size:].copy()
        else:
            self.audio = self.audio[-self.max_size:].copy()
        return list(results.values())
