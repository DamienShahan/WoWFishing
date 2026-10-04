"""Windows WASAPI loopback capture with bounded buffering and explicit errors."""
from queue import Empty, Full, Queue

import numpy as np


class AudioBackend:
    def __enter__(self):
        try:
            import pyaudiowpatch as pyaudio
        except ImportError as exc:
            raise RuntimeError("WASAPI recording requires Windows and PyAudioWPatch") from exc
        self.api = pyaudio
        self.p = pyaudio.PyAudio()
        return self

    def __exit__(self, *args):
        self.p.terminate()

    def device(self, index=None):
        info = self.p.get_default_wasapi_loopback() if index is None else self.p.get_device_info_by_index(index)
        if not info.get("isLoopbackDevice") or info["maxInputChannels"] < 1:
            raise ValueError("Select a WASAPI loopback device using listen.py --list-devices")
        return info

    def capture(self, device, chunk_seconds):
        return Capture(self, device, chunk_seconds)


class Capture:
    def __init__(self, backend, device, chunk_seconds):
        self.backend = backend
        self.device = device
        self.rate = int(device["defaultSampleRate"])
        self.channels = int(device["maxInputChannels"])
        self.frames = max(1, round(self.rate * chunk_seconds))
        self.queue = Queue(maxsize=64)
        self.error = None
        self.stream = None

    def _callback(self, data, frames, time_info, status):
        api = self.backend.api
        if status:
            self.error = RuntimeError(f"Audio discontinuity (PortAudio status {status}); capture stopped")
            return None, api.paAbort
        if data:
            try:
                self.queue.put_nowait(data)
            except Full:
                self.error = RuntimeError("Audio processing fell behind; capture queue overflowed")
                return None, api.paAbort
        return None, api.paContinue

    def __enter__(self):
        self.stream = self.backend.p.open(
            format=self.backend.api.paInt16, channels=self.channels,
            rate=self.rate, input=True, input_device_index=int(self.device["index"]),
            frames_per_buffer=self.frames, stream_callback=self._callback,
        )
        return self

    def read(self, timeout=3):
        if self.error:
            raise self.error
        try:
            data = self.queue.get(timeout=timeout)
        except Empty as exc:
            if self.error:
                raise self.error
            raise RuntimeError("No loopback audio received for 3 seconds; check output device and game audio") from exc
        if self.error:
            raise self.error
        return np.frombuffer(data, dtype=np.int16).reshape(-1, self.channels).astype(np.float64) / 32768

    def __exit__(self, *args):
        if self.stream is not None:
            try:
                if self.stream.is_active():
                    self.stream.stop_stream()
            finally:
                self.stream.close()


def describe(device):
    return f"[{int(device['index'])}] {device['name']} ({int(device['defaultSampleRate'])} Hz, {int(device['maxInputChannels'])} channels)"
