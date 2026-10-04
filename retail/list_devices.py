"""List only output loopback devices suitable for this program."""
from audio_io import AudioBackend, describe


def main():
    with AudioBackend() as backend:
        try:
            default_index = backend.device()["index"]
        except (OSError, ValueError):
            default_index = None
        devices = list(backend.p.get_loopback_device_info_generator())
        if not devices:
            raise RuntimeError("No WASAPI loopback devices found")
        for device in devices:
            marker = " [DEFAULT]" if device["index"] == default_index else ""
            print(describe(device) + marker)
        print("Set audio.device_index in settings.yaml, or use null for DEFAULT.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
