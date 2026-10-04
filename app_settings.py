"""Validated, atomically saved settings shared by the GUI and bot controller."""
from copy import deepcopy
from math import isfinite
from pathlib import Path
import os
import re
import sys

import yaml

DEFAULTS = {
    "ACTION_KEY": "k", "LURE_KEY": "f5", "USE_LURE": False,
    "WOW_TITLE_REGEX": "^World of Warcraft$",
    "OUTPUT_DEVICE_INDEX": None, "OUTPUT_DEVICE_NAME": None,
    "WAIT_AFTER_NOT_FOUND": [0.5, 1.5],
    "WAIT_AFTER_TARGET_FOUND": [3.0, 5.0],
    "LURE_WAIT_TIME": [5.1, 5.5], "LURE_COOLDOWN_SECONDS": 610.0,
    "LISTEN_DURATION": 23.0, "THRESHOLD": 0.40,
    "STOP_AUTOMATICALLY": False, "STOP_AFTER_MINUTES": 30.0,
}
KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {
    "space", "enter", "tab", "esc", "up", "down", "left", "right",
    "home", "end", "pageup", "pagedown", "insert", "delete",
} | {f"f{i}" for i in range(1, 25)}
RANGES = ("WAIT_AFTER_NOT_FOUND", "WAIT_AFTER_TARGET_FOUND", "LURE_WAIT_TIME")


def settings_path():
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("APPDATA", Path.home())) / "WoWFishing" / "settings.yaml"
    return Path(__file__).resolve().with_name("settings.yaml")


def validate(values):
    if not isinstance(values, dict):
        raise ValueError("Settings must be a YAML mapping.")
    unknown = set(values) - set(DEFAULTS)
    if unknown:
        raise ValueError("Unknown settings: " + ", ".join(sorted(map(str, unknown))))
    cfg = deepcopy(DEFAULTS)
    cfg.update(values)
    for name in ("ACTION_KEY", "LURE_KEY"):
        if not isinstance(cfg[name], str) or cfg[name].strip().lower() not in KEYS:
            raise ValueError(f"{name}: use one key, such as k, space, or f5.")
        cfg[name] = cfg[name].strip().lower()
    for name in ("USE_LURE", "STOP_AUTOMATICALLY"):
        if type(cfg[name]) is not bool:
            raise ValueError(f"{name} must be true or false.")

    def number(value, name, minimum, maximum):
        try:
            result = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be a number.") from None
        if isinstance(value, bool) or not isfinite(result) or not minimum <= result <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}.")
        return result

    for name in RANGES:
        value = cfg[name]
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError(f"{name} needs a minimum and maximum in seconds.")
        lo, hi = [number(v, name, 0, 3600) for v in value]
        if lo > hi:
            raise ValueError(f"{name}: minimum cannot exceed maximum.")
        cfg[name] = [lo, hi]
    for name, lo, hi in (("LISTEN_DURATION", 1, 120), ("THRESHOLD", .01, 1),
                         ("LURE_COOLDOWN_SECONDS", 1, 86400), ("STOP_AFTER_MINUTES", .01, 10080)):
        cfg[name] = number(cfg[name], name, lo, hi)
    index = cfg["OUTPUT_DEVICE_INDEX"]
    if index is not None and (type(index) is not int or index < 0):
        raise ValueError("OUTPUT_DEVICE_INDEX must be a nonnegative integer or null.")
    if cfg["OUTPUT_DEVICE_NAME"] is not None and not isinstance(cfg["OUTPUT_DEVICE_NAME"], str):
        raise ValueError("OUTPUT_DEVICE_NAME must be a device name or null.")
    if not isinstance(cfg["WOW_TITLE_REGEX"], str) or not cfg["WOW_TITLE_REGEX"]:
        raise ValueError("WOW_TITLE_REGEX must contain a window title pattern.")
    try:
        re.compile(cfg["WOW_TITLE_REGEX"])
    except re.error as exc:
        raise ValueError(f"Invalid window title pattern: {exc}") from exc
    return cfg


def load(path):
    path = Path(path)
    if (getattr(sys, "frozen", False) and path == settings_path() and not path.exists()):
        # Keep existing preferences on the first launch under the new app name.
        legacy = path.parent.parent / "ToxicFishing" / "settings.yaml"
        if legacy.exists():
            path = legacy
    if not path.exists():
        return deepcopy(DEFAULTS)
    try:
        return validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid settings.yaml: {exc}") from exc


def save(path, values):
    cfg = validate(values)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".yaml.tmp")
    temporary.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    temporary.replace(path)
    return cfg
