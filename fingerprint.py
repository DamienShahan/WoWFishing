"""Small landmark matcher for short sound effects; no capture or keyboard actions."""
from dataclasses import dataclass
from itertools import product
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import ndimage, signal

RATE = 16000
WINDOW = 512
HOP = 160  # 10 ms


def mono_resample(audio, rate):
    audio = np.asarray(audio, dtype=np.float64)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if audio.ndim != 1 or not np.isfinite(audio).all():
        raise ValueError("Expected finite mono or stereo audio")
    if rate != RATE:
        divisor = gcd(int(rate), RATE)
        audio = signal.resample_poly(audio, RATE // divisor, int(rate) // divisor)
    return audio


def read_audio(path):
    audio, rate = sf.read(path, always_2d=True)
    return mono_resample(audio, rate)


def landmarks(audio):
    """Sparse peaks and peak pairs. Hash = two frequencies + elapsed time."""
    if len(audio) < WINDOW or np.std(audio) < 1e-5:
        return np.empty((0, 2), dtype=int), []
    _, _, spectrum = signal.stft(
        audio, RATE, nperseg=WINDOW, noverlap=WINDOW-HOP,
        boundary=None, padded=False,
    )
    db = 20 * np.log10(np.maximum(np.abs(spectrum), 1e-10))
    mask = (db == ndimage.maximum_filter(db, size=(7, 7))) & (db > db.max()-40)
    mask[:5] = False  # Ignore frequencies below about 156 Hz.
    frequency, frame = np.nonzero(mask)
    # Limit density to three strong peaks per 30 ms region.
    selected = []
    for region in np.unique(frame // 3):
        candidates = np.flatnonzero(frame // 3 == region)
        chosen = candidates[np.argsort(db[frequency[candidates], frame[candidates]])[-3:]]
        selected.extend((int(frame[i]), int(frequency[i])) for i in chosen)
    peaks = np.array(sorted(selected), dtype=int).reshape(-1, 2)
    pairs = []
    for anchor, (time, freq) in enumerate(peaks):
        # Four target zones provide relationships across different time scales.
        for lo, hi in ((5, 11), (11, 19), (19, 29), (29, 41)):
            targets = np.flatnonzero((peaks[:, 0]-time >= lo) & (peaks[:, 0]-time < hi))
            if not len(targets):
                continue
            strength = db[peaks[targets, 1], peaks[targets, 0]]
            for target in targets[np.argsort(strength)[-2:]]:
                target_time, target_freq = peaks[target]
                key = (int(freq)//2, int(target_freq)//2, int(target_time-time)//2)
                pairs.append((key, anchor, int(target), int(time)))
    return peaks, pairs


@dataclass
class Reference:
    name: str
    duration: float
    crop_start: float
    peaks: np.ndarray
    pairs: list
    anchors: set


@dataclass
class Match:
    name: str
    score: float
    anchors: int
    span: float
    start: float
    end: float
    speed: float = 1.0


class FingerprintDetector:
    def __init__(self, paths, duration=None, threshold=0.40, min_anchors=8,
                 speed_tolerance=0.12):
        if not np.isfinite(speed_tolerance) or not 0 <= speed_tolerance <= 0.25:
            raise ValueError("speed_tolerance must be between 0 and 0.25")
        self.threshold = threshold
        self.min_anchors = min_anchors
        self.references = []
        for path in paths:
            audio = read_audio(path)
            if len(audio) < WINDOW or np.std(audio) < 1e-5:
                raise ValueError(f"Reference is empty, too short, or silent: {path}")
            # Remove quiet padding only; never modify the source WAV.
            frame_energy = np.convolve(audio**2, np.ones(160)/160, mode="same")
            active = np.flatnonzero(frame_energy >= frame_energy.max()*0.01)
            start = max(0, int(active[0])-800)
            end = min(len(audio), int(active[-1])+801)
            if duration is not None:
                end = min(end, start+round(duration*RATE))
            excerpt = audio[start:end]
            peaks, pairs = landmarks(excerpt)
            anchors = {pair[1] for pair in pairs}
            if len(anchors) < min_anchors:
                raise ValueError(f"Too few landmarks in {path}; use a longer reference")
            ref = Reference(Path(path).name, len(excerpt)/RATE, start/RATE, peaks, pairs, anchors)
            self.references.append(ref)
        if not self.references:
            raise ValueError("No reference WAVs found")
        steps = int(np.ceil(speed_tolerance/0.01))
        self.speeds = (np.linspace(1-speed_tolerance, 1+speed_tolerance, 2*steps+1)
                       if steps else np.array([1.0]))
        self.max_duration = max(ref.duration for ref in self.references)/self.speeds[0]
        # Respeed the landmark geometry once, not the live waveform on every block.
        # Playback rate s maps frequency -> f*s and time -> t/s.
        keys, variants, anchors, targets, frames = [], [], [], [], []
        self.variants = []
        for ref_id, ref in enumerate(self.references):
            for speed in self.speeds:
                variant = len(self.variants)
                self.variants.append((ref_id, float(speed)))
                for _, anchor, target, _ in ref.pairs:
                    time, freq = ref.peaks[anchor]
                    target_time, target_freq = ref.peaks[target]
                    f1, f2 = int(freq*speed)//2, int(target_freq*speed)//2
                    dt = int((target_time-time)/speed)//2
                    keys.append((f1 << 20) | (f2 << 10) | dt)
                    variants.append(variant)
                    anchors.append(anchor)
                    targets.append(target)
                    frames.append(time/speed)
        order = np.argsort(keys)
        self.keys = np.asarray(keys, dtype=np.int64)[order]
        self.variant_ids = np.asarray(variants, dtype=np.int32)[order]
        self.anchor_ids = np.asarray(anchors, dtype=np.int32)[order]
        self.target_ids = np.asarray(targets, dtype=np.int32)[order]
        self.reference_frames = np.asarray(frames)[order]
        self.key_neighbors = np.array([(a << 20)+(b << 10)+c
                                       for a, b, c in product((-1, 0, 1), repeat=3)])

    def match(self, audio, origin=0.0, end_after=-float("inf")):
        """Return the best aligned candidate for each reference.

        Score is the fraction of unique reference anchors supported by pairs,
        NOT a probability. Offset voting tolerates a few STFT frames of jitter.
        """
        _, pairs = landmarks(audio)
        if not pairs:
            return []
        query_keys = np.array([(key[0] << 20) | (key[1] << 10) | key[2]
                               for key, _, _, _ in pairs], dtype=np.int64)
        lookups = (query_keys[:, None]+self.key_neighbors).ravel()
        left = np.searchsorted(self.keys, lookups, side="left")
        right = np.searchsorted(self.keys, lookups, side="right")
        counts = right-left
        total = int(counts.sum())
        if not total:
            return []
        # Batch all fuzzy hash lookups and offset votes in NumPy. This keeps the
        # rate hypotheses out of the per-pair Python hot loop.
        lookup_ids = np.repeat(np.arange(len(lookups)), counts)
        starts = np.repeat(np.cumsum(counts)-counts, counts)
        entries = left[lookup_ids]+np.arange(total)-starts
        query_frames = np.array([pair[3] for pair in pairs])
        offsets = np.rint(query_frames[lookup_ids//27]-self.reference_frames[entries]).astype(int)
        variant_ids = self.variant_ids[entries]
        order = np.argsort(variant_ids)
        entries, offsets, variant_ids = entries[order], offsets[order], variant_ids[order]
        unique, begins, sizes = np.unique(variant_ids, return_index=True, return_counts=True)
        results = {}
        for variant, begin, size in zip(unique, begins, sizes):
            ref_id, speed = self.variants[variant]
            ref = self.references[ref_id]
            duration = ref.duration/speed
            local_entries = entries[begin:begin+size]
            local_offsets = offsets[begin:begin+size]
            low, high = int(local_offsets.min())-2, int(local_offsets.max())+2
            histogram = np.bincount(local_offsets-low, minlength=high-low+1)
            support = np.convolve(histogram, np.ones(5, dtype=int), mode="same")
            starts_seconds = origin + np.arange(low, high+1)*HOP/RATE
            ends_seconds = starts_seconds+duration
            eligible = ((starts_seconds >= origin-0.04)
                        & (ends_seconds <= origin+len(audio)/RATE+0.04)
                        & (ends_seconds > end_after))
            support[~eligible] = 0
            # Verify the strongest distinct alignments, counting each reference
            # pair once so repeated lookup hits cannot inflate the score.
            for _ in range(3):
                index = int(support.argmax())
                if support[index] < self.min_anchors*2:
                    break
                offset = index+low
                selected = local_entries[np.abs(local_offsets-offset) <= 2]
                pair_ids = self.anchor_ids[selected]*len(ref.peaks)+self.target_ids[selected]
                anchor_ids, pair_counts = np.unique(np.unique(pair_ids)//len(ref.peaks), return_counts=True)
                supported = anchor_ids[pair_counts >= 2]
                support[max(0, index-4):index+5] = 0
                if not len(supported):
                    continue
                times = ref.peaks[supported, 0]*HOP/RATE/speed
                candidate = Match(ref.name, len(supported)/len(ref.anchors), len(supported),
                                  float(np.ptp(times)), float(starts_seconds[index]),
                                  float(ends_seconds[index]), speed)
                if ref_id not in results or candidate.score > results[ref_id].score:
                    results[ref_id] = candidate
        return sorted(results.values(), key=lambda match: match.score, reverse=True)

    def accepts(self, match):
        ref = next(ref for ref in self.references if ref.name == match.name)
        return (match.score >= self.threshold and match.anchors >= self.min_anchors
                and match.span >= min(0.35, ref.duration/match.speed*0.4))


class StreamDetector:
    """Bounded buffer at the capture rate; resampling happens on whole windows."""
    def __init__(self, detector, rate, cooldown=2.0):
        self.detector, self.rate, self.cooldown = detector, rate, cooldown
        self.buffer = np.empty(0)
        self.total = 0
        self.last_event = -float("inf")
        self.keep = round((detector.max_duration+0.6)*rate)

    def process(self, chunk):
        chunk = np.asarray(chunk, dtype=float)
        if chunk.ndim == 2:
            chunk = chunk.mean(axis=1)
        if chunk.ndim != 1 or not np.isfinite(chunk).all():
            raise ValueError("Capture contains invalid samples")
        if not len(chunk):
            return [], None
        previous_time = self.total/self.rate
        self.total += len(chunk)
        self.buffer = np.concatenate((self.buffer, chunk))[-self.keep:]
        origin = (self.total-len(self.buffer))/self.rate
        matches = self.detector.match(mono_resample(self.buffer, self.rate), origin,
                                      end_after=previous_time-0.08)
        found = next((m for m in matches if self.detector.accepts(m)
                      and m.end-self.last_event >= self.cooldown), None)
        if found:
            self.last_event = found.end
        return matches, found
