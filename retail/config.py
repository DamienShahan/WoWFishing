"""Validated configuration, with paths independent of the working directory."""
from pathlib import Path
import math
import yaml

DEFAULT_CONFIG = Path(__file__).with_name("settings.yaml")
EVENT_NAMES = ("target", "out_of_range")


def _number(section, key, low, high=None, strict_low=False):
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    if not math.isfinite(value) or value < low or (strict_low and value == low):
        raise ValueError(f"{key} must be {'greater than' if strict_low else 'at least'} {low}")
    if high is not None and value > high:
        raise ValueError(f"{key} must be at most {high}")


def load_config(path=DEFAULT_CONFIG):
    path = Path(path).resolve()
    with path.open(encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    try:
        audio, detection, events, auto = (cfg[k] for k in ("audio", "detection", "events", "automation"))
        index = audio["device_index"]
        if index is not None and (type(index) is not int or index < 0):
            raise ValueError("device_index must be null or a nonnegative integer")
        _number(audio, "chunk_seconds", 0.02, 0.5)
        _number(audio, "min_rms", 0, 1, strict_low=True)
        if detection["mode"] not in ("waveform", "spectral"):
            raise ValueError("mode must be waveform or spectral")
        _number(detection, "cooldown_seconds", 0)
        _number(detection, "ambiguity_margin", 0, 1)
        if type(detection["spectral_bands"]) is not int:
            raise ValueError("spectral_bands must be an integer")
        _number(detection, "spectral_bands", 8, 128)
        _number(detection, "spectral_window_ms", 10, 100)
        _number(detection, "spectral_hop_ms", 1, detection["spectral_window_ms"])
        _number(detection, "pcen_time_constant", 0, strict_low=True)
        if set(events) != set(EVENT_NAMES):
            raise ValueError("events must contain target and out_of_range")
        for name, event in events.items():
            if type(event["enabled"]) is not bool:
                raise ValueError(f"{name}.enabled must be true or false")
            if not isinstance(event["templates"], str) or not event["templates"].strip():
                raise ValueError(f"{name}.templates must be a glob path")
            for method in ("waveform", "spectral"):
                _number(event, method + "_threshold", 0, 1, strict_low=True)
        if not events["target"]["enabled"]:
            raise ValueError("target must be enabled")
        for key in ("window_title_regex", "action_key", "lure_key"):
            if not isinstance(auto[key], str) or not auto[key].strip():
                raise ValueError(f"{key} must be a nonempty string")
        import re
        re.compile(auto["window_title_regex"])
        if type(auto["use_lure"]) is not bool:
            raise ValueError("use_lure must be true or false (without quotes)")
        for key in ("listen_seconds", "lure_interval_seconds"):
            _number(auto, key, 0, strict_low=True)
        _number(auto, "target_guard_seconds", 0, auto["listen_seconds"])
        for key in ("wait_after_target", "wait_after_out_of_range", "wait_after_timeout", "lure_wait"):
            values = auto[key]
            if not isinstance(values, list) or len(values) != 2:
                raise ValueError(f"{key} must contain [minimum, maximum]")
            _number({"minimum": values[0]}, "minimum", 0)
            _number({"maximum": values[1]}, "maximum", values[0])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Invalid or missing setting in {path}: {exc}") from exc
    cfg["config_dir"] = path.parent
    return cfg
