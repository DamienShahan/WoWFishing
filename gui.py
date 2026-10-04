"""WoWFishing desktop entry point. The CLI listener remains listen.py."""
import argparse
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
import re
from threading import Thread
import time
from tkinter import messagebox

import customtkinter as ctk

from app_settings import RANGES, load, save, settings_path, validate
from audio_io import AudioBackend
from bot import BotSession
from windows_control import list_windows

BG = "#13131f"
PANEL = "#1e1e2e"
FIELD = "#28283c"
LINE = "#36364f"
TEXT = "#f2f3ff"
MUTED = "#969bb8"
GREEN = "#38b64b"
DEFAULT_AUDIO = "Default Windows output"
NO_WINDOW = "Open WoW, then refresh"


class App(ctk.CTk):
    def __init__(self, config_path=None):
        super().__init__()
        self.title("WoWFishing")
        self.geometry("1180x790")
        self.minsize(940, 720)
        self.configure(fg_color=BG)
        self.path = Path(config_path) if config_path else settings_path()
        self.config_error = None
        try:
            self.settings = load(self.path)
        except (ValueError, OSError) as exc:
            self.settings = validate({})
            self.config_error = str(exc)
        self.events = Queue()
        self.worker = self.session = None
        self.scanner = None
        self.started = None
        self.closing = False
        self.had_error = False
        self.dialog = None
        self.windows = {}
        self.devices = {DEFAULT_AUDIO: None}
        self.controls = []
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(80, self.poll)
        self.after(150, self.initialize)

    def initialize(self):
        self.log("Ready. Choose your game window and audio output, then start.")
        self.log(f"Settings: {self.path}")
        if self.config_error:
            self.log(f"Settings could not be loaded: {self.config_error}")
            self.log("Fix the file and restart, or open Settings and save corrected values.")
        elif not self.path.exists():
            try:
                save(self.path, self.settings)
            except OSError as exc:
                self.log(f"Could not create settings: {exc}")
        self.refresh()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(22, 18))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="WoWFishing", font=("Segoe UI", 23, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text="Automated fishing assistant", text_color=MUTED, font=("Segoe UI", 12)).grid(row=1, column=0, sticky="w")
        self.status = ctk.CTkLabel(header, text="●  Stopped", fg_color=PANEL, corner_radius=16, width=140, height=34, text_color=MUTED)
        self.status.grid(row=0, column=1, rowspan=2, padx=(12, 0))
        self.settings_button = ctk.CTkButton(header, text="Settings", width=96, height=34, fg_color=FIELD, hover_color=LINE, command=self.open_settings)
        self.settings_button.grid(row=0, column=2, rowspan=2, padx=(12, 0))

        side = ctk.CTkScrollableFrame(self, width=280, fg_color=PANEL, border_color=LINE, border_width=1, corner_radius=14)
        side.grid(row=1, column=0, sticky="nsew", padx=(20, 16), pady=(0, 20))
        side.grid_columnconfigure(0, weight=1)
        self.start_button = ctk.CTkButton(side, text="▶  Start bot", height=46, font=("Segoe UI", 14, "bold"), fg_color=GREEN, hover_color="#2c983d", command=self.toggle)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 14))
        self.caption(side, "UPTIME", 1)
        self.uptime = ctk.CTkLabel(side, text="00:00:00", font=("Consolas", 24, "bold"), anchor="w")
        self.uptime.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 12))
        self.separator(side, 3)
        self.caption(side, "SCHEDULED RUN TIME", 4)
        self.auto = ctk.BooleanVar(value=self.settings["STOP_AUTOMATICALLY"])
        self.auto_check = ctk.CTkCheckBox(side, text="Stop automatically", variable=self.auto, command=self.main_changed, checkbox_width=18, checkbox_height=18, font=("Segoe UI", 13))
        self.auto_check.grid(row=5, column=0, sticky="w", padx=20, pady=(4, 10))
        timing = ctk.CTkFrame(side, fg_color="transparent")
        timing.grid(row=6, column=0, sticky="ew", padx=20)
        self.minutes = ctk.CTkEntry(timing, width=90, height=36, fg_color=FIELD, border_color=LINE)
        self.minutes.insert(0, f"{self.settings['STOP_AFTER_MINUTES']:g}")
        self.minutes.pack(side="left")
        self.minutes.bind("<FocusOut>", lambda _: self.main_changed())
        ctk.CTkLabel(timing, text="minutes", text_color=MUTED).pack(side="left", padx=12)
        self.separator(side, 7)
        self.caption(side, "GAME WINDOW", 8)
        self.window_combo = ctk.CTkComboBox(side, values=[NO_WINDOW], width=280, height=36, state="readonly", fg_color=FIELD, border_color=LINE, button_color=LINE, command=self.main_changed)
        self.window_combo.set(NO_WINDOW)
        self.window_combo.grid(row=9, column=0, sticky="ew", padx=20, pady=(6, 12))
        self.caption(side, "AUDIO OUTPUT", 10)
        self.audio_combo = ctk.CTkComboBox(side, values=[DEFAULT_AUDIO], width=280, height=36, state="readonly", fg_color=FIELD, border_color=LINE, button_color=LINE, command=self.main_changed)
        self.audio_combo.set(DEFAULT_AUDIO)
        self.audio_combo.grid(row=11, column=0, sticky="ew", padx=20, pady=(6, 6))
        ctk.CTkLabel(side, text="Select the output playing your game audio.", text_color=MUTED, font=("Segoe UI", 11), anchor="w").grid(row=12, column=0, sticky="w", padx=20)
        self.refresh_button = ctk.CTkButton(side, text="↻  Refresh windows & devices", height=36, fg_color=FIELD, hover_color=LINE, command=self.refresh)
        self.refresh_button.grid(row=13, column=0, sticky="ew", padx=20, pady=(10, 0))
        self.separator(side, 14)
        self.lure = ctk.BooleanVar(value=self.settings["USE_LURE"])
        self.lure_check = ctk.CTkCheckBox(side, text="Use lure", variable=self.lure, command=self.main_changed, checkbox_width=18, checkbox_height=18)
        self.lure_check.grid(row=15, column=0, sticky="w", padx=20, pady=(4, 6))
        self.keys_label = ctk.CTkLabel(side, text="", text_color=MUTED, font=("Segoe UI", 12), anchor="w")
        self.keys_label.grid(row=16, column=0, sticky="ew", padx=20, pady=(0, 16))
        self.update_keys()
        side.grid_rowconfigure(17, weight=1)

        activity = ctk.CTkFrame(self, fg_color=PANEL, border_color=LINE, border_width=1, corner_radius=14)
        activity.grid(row=1, column=1, sticky="nsew", padx=(0, 20), pady=(0, 20))
        activity.grid_columnconfigure(0, weight=1)
        activity.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(activity, text="ACTIVITY", text_color=MUTED, font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w", padx=20, pady=18)
        ctk.CTkButton(activity, text="Clear", width=76, height=30, fg_color=FIELD, hover_color=LINE, command=self.clear_log).grid(row=0, column=1, padx=20)
        self.log_box = ctk.CTkTextbox(activity, fg_color=BG, border_width=1, border_color=LINE, corner_radius=8, font=("Consolas", 12), wrap="word", state="disabled")
        self.log_box.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=20, pady=(0, 20))
        self.controls = [self.auto_check, self.minutes, self.window_combo, self.audio_combo,
                         self.refresh_button, self.lure_check, self.settings_button]

    @staticmethod
    def caption(parent, text, row):
        ctk.CTkLabel(parent, text=text, text_color=MUTED, font=("Segoe UI", 11), anchor="w").grid(row=row, column=0, sticky="w", padx=20, pady=(7, 0))

    @staticmethod
    def separator(parent, row):
        ctk.CTkFrame(parent, fg_color=LINE, height=1, corner_radius=0).grid(row=row, column=0, sticky="ew", padx=20, pady=(16, 8))

    def update_keys(self):
        self.keys_label.configure(text=f"Action: {self.settings['ACTION_KEY'].upper()}    ·    Lure: {self.settings['LURE_KEY'].upper()}")

    def log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{datetime.now():%H:%M:%S}] {text}\n")
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > 1500:
            self.log_box.delete("1.0", f"{lines - 1500}.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def snapshot(self):
        cfg = deepcopy(self.settings)
        cfg.update(USE_LURE=self.lure.get(), STOP_AUTOMATICALLY=self.auto.get(),
                   STOP_AFTER_MINUTES=self.minutes.get())
        window = self.windows.get(self.window_combo.get())
        if window:
            cfg["WOW_TITLE_REGEX"] = "^" + re.escape(window.title) + "$"
        label = self.audio_combo.get()
        if label in self.devices:
            device = self.devices[label]
            cfg["OUTPUT_DEVICE_INDEX"] = int(device["index"]) if device else None
            cfg["OUTPUT_DEVICE_NAME"] = device["name"] if device else None
        return validate(cfg)

    def main_changed(self, *_):
        if self.worker or self.config_error:
            return
        try:
            self.settings = save(self.path, self.snapshot())
        except (ValueError, OSError) as exc:
            self.log(f"Settings not saved: {exc}")

    def refresh(self):
        if self.worker or (self.scanner and self.scanner.is_alive()):
            return
        self.refresh_button.configure(state="disabled", text="Refreshing…")
        self.start_button.configure(state="disabled")

        def scan():
            windows, devices, errors = [], None, []
            try:
                windows = list_windows()
            except Exception as exc:
                errors.append(f"Window discovery failed: {exc}")
            try:
                with AudioBackend() as backend:
                    devices = list(backend.p.get_loopback_device_info_generator())
            except Exception as exc:
                errors.append(f"Audio discovery failed: {exc}")
            self.events.put(("discovery", (windows, devices, errors)))
        self.scanner = Thread(target=scan, daemon=True)
        self.scanner.start()

    def discovered(self, result):
        windows, devices, errors = result
        previous = self.window_combo.get()
        self.windows = {window.label: window for window in windows}
        choices = list(self.windows) or [NO_WINDOW]
        self.window_combo.configure(values=choices)
        matches = [w.label for w in windows if re.search(self.settings["WOW_TITLE_REGEX"], w.title)]
        selected = previous if previous in self.windows else (matches[0] if len(matches) == 1 else "Select a game window")
        self.window_combo.set(selected if windows else NO_WINDOW)
        self.devices = {DEFAULT_AUDIO: None} if devices is not None else {}
        for device in devices or []:
            self.devices[f"[{int(device['index'])}] {device['name']}"] = device
        self.audio_combo.configure(values=list(self.devices) or ["No audio devices available"])
        saved_name = self.settings["OUTPUT_DEVICE_NAME"]
        saved_index = self.settings["OUTPUT_DEVICE_INDEX"]
        matches = [label for label, d in self.devices.items() if d and d["name"] == saved_name]
        exact = [label for label in matches if int(self.devices[label]["index"]) == saved_index]
        if saved_name:
            selected = exact[0] if exact else (matches[0] if len(matches) == 1 else "Saved output unavailable — select output")
        elif saved_index is not None:
            selected = "Select audio output again"
        else:
            selected = DEFAULT_AUDIO if devices is not None else "No audio devices available"
        self.audio_combo.set(selected)
        self.refresh_button.configure(state="normal", text="↻  Refresh windows & devices")
        self.start_button.configure(state="normal")
        for error in errors:
            self.log(error)

    def toggle(self):
        if self.worker:
            self.request_stop()
            return
        try:
            if self.config_error:
                raise ValueError("Fix settings.yaml and restart, or open Settings and save corrected values first.")
            if self.window_combo.get() not in self.windows:
                raise ValueError("Select a World of Warcraft window. Open the game and refresh if needed.")
            if self.audio_combo.get() not in self.devices:
                raise ValueError("Select an available audio output.")
            self.settings = save(self.path, self.snapshot())
        except (ValueError, OSError) as exc:
            messagebox.showerror("Cannot start", str(exc), parent=self)
            return
        self.session = BotSession(self.settings, self.windows[self.window_combo.get()],
                                  lambda kind, value: self.events.put((kind, value)))
        self.had_error = False
        self.started = time.monotonic()
        for control in self.controls:
            control.configure(state="disabled")
        self.start_button.configure(text="■  Stop bot", fg_color="#ca505b", hover_color="#a73e48")
        self.status.configure(text="●  Starting", text_color=GREEN)
        self.worker = Thread(target=self.session.run, name="fishing-worker", daemon=False)
        self.worker.start()

    def request_stop(self):
        if self.session:
            self.session.stop()
            self.status.configure(text="●  Stopping", text_color=MUTED)
            self.start_button.configure(state="disabled", text="Stopping…")

    def poll(self):
        for _ in range(150):
            try:
                kind, value = self.events.get_nowait()
            except Empty:
                break
            if kind == "log":
                self.log(value)
            elif kind == "state" and self.session and not self.session.stop_event.is_set():
                self.status.configure(text=f"●  {value}", text_color=GREEN)
            elif kind == "error":
                self.had_error = True
                self.log(f"ERROR: {value}")
            elif kind == "discovery":
                self.discovered(value)
        if self.worker:
            elapsed = int(time.monotonic() - self.started)
            self.uptime.configure(text=f"{elapsed // 3600:02}:{elapsed // 60 % 60:02}:{elapsed % 60:02}")
            if not self.worker.is_alive() and self.events.empty():
                self.worker.join()
                self.worker = self.session = None
                for control in self.controls:
                    control.configure(state="readonly" if control in (self.window_combo, self.audio_combo) else "normal")
                self.start_button.configure(state="normal", text="▶  Start bot", fg_color=GREEN, hover_color="#2c983d")
                self.status.configure(text="●  Error" if self.had_error else "●  Stopped", text_color="#f08088" if self.had_error else MUTED)
        if self.closing and not self.worker and not (self.scanner and self.scanner.is_alive()):
            self.destroy()
            return
        self.after(80, self.poll)

    def open_settings(self):
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.focus()
            return
        self.dialog = SettingsDialog(self)

    def close(self):
        if self.closing:
            return
        self.main_changed()
        self.closing = True
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.destroy()
        self.request_stop()
        self.start_button.configure(state="disabled")
        for control in self.controls:
            control.configure(state="disabled")


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("WoWFishing · Settings")
        self.geometry("570x690")
        self.minsize(520, 500)
        self.configure(fg_color=BG)
        self.transient(app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text="Settings", font=("Segoe UI", 23, "bold"), anchor="w").grid(row=0, column=0, sticky="w", padx=24, pady=(20, 12))
        body = ctk.CTkScrollableFrame(self, fg_color=PANEL, corner_radius=12)
        body.grid(row=1, column=0, sticky="nsew", padx=20)
        body.grid_columnconfigure(1, weight=1)
        self.entries = {}
        fields = [
            ("ACTION_KEY", "Action key", "Casts and reels in using the same key."),
            ("LURE_KEY", "Lure key", "Bind this to your in-game lure macro."),
            ("WAIT_AFTER_TARGET_FOUND", "After a bite (seconds)", "Minimum and maximum wait before recasting."),
            ("WAIT_AFTER_NOT_FOUND", "After timeout (seconds)", "Minimum and maximum wait before retrying."),
            ("LURE_WAIT_TIME", "Lure cast wait (seconds)", "Allow the lure cast to finish before fishing."),
            ("LURE_COOLDOWN_SECONDS", "Lure interval (seconds)", "Reapply at the next cycle after this interval."),
            ("LISTEN_DURATION", "Cast timeout (seconds)", "Recast if no bite is detected in this time."),
            ("THRESHOLD", "Detection threshold", "0.01–1.00; higher requires a stronger match."),
        ]
        for row, (key, label, hint) in enumerate(fields):
            ctk.CTkLabel(body, text=label, anchor="w", font=("Segoe UI", 13, "bold")).grid(row=row*2, column=0, sticky="w", padx=12, pady=(12, 0))
            holder = ctk.CTkFrame(body, fg_color="transparent")
            holder.grid(row=row*2, column=1, sticky="e", padx=12, pady=(12, 0))
            values = app.settings[key] if key in RANGES else [app.settings[key]]
            entries = []
            for index, value in enumerate(values):
                if index:
                    ctk.CTkLabel(holder, text="to", width=22).pack(side="left")
                entry = ctk.CTkEntry(holder, width=70 if key in RANGES else 150, fg_color=FIELD, border_color=LINE)
                entry.insert(0, str(value))
                entry.pack(side="left")
                entries.append(entry)
            self.entries[key] = entries
            ctk.CTkLabel(body, text=hint, text_color=MUTED, font=("Segoe UI", 11), anchor="w").grid(row=row*2+1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 3))
        ctk.CTkLabel(body, text="Keys: letters, numbers, F1–F24, space, or navigation keys.\nBind the action key to your fishing action in WoW first.", text_color=MUTED, justify="left", font=("Segoe UI", 11)).grid(row=17, column=0, columnspan=2, sticky="w", padx=12, pady=16)
        self.error = ctk.CTkLabel(self, text="", text_color="#f08088", wraplength=510, justify="left")
        self.error.grid(row=2, column=0, sticky="ew", padx=24, pady=(6, 0))
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="e", padx=20, pady=(6, 20))
        ctk.CTkButton(footer, text="Cancel", width=100, fg_color=FIELD, hover_color=LINE, command=self.destroy).pack(side="left", padx=10)
        ctk.CTkButton(footer, text="Save settings", width=130, fg_color=GREEN, hover_color="#2c983d", command=self.commit).pack(side="left")
        self.after(100, self.grab_set)

    def commit(self):
        try:
            cfg = self.app.snapshot()
            for key, entries in self.entries.items():
                cfg[key] = [entry.get() for entry in entries] if key in RANGES else entries[0].get()
            self.app.settings = save(self.app.path, cfg)
        except (ValueError, OSError) as exc:
            self.error.configure(text=str(exc))
            return
        self.app.config_error = None
        self.app.update_keys()
        self.app.log("Settings saved.")
        self.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, help="Use a specific settings.yaml (for portable use or testing)")
    parser.add_argument("--self-check", type=Path, metavar="REPORT", help="Check bundled resources and device discovery without sending keys; write a JSON report")
    args = parser.parse_args()
    if args.self_check:
        import json
        import pyautogui
        from fingerprint import FingerprintDetector, read_audio
        paths = [Path(__file__).resolve().parent / "sounds" / "target" / f"bite{i}.wav" for i in (1, 2, 4)]
        detector = FingerprintDetector(paths)
        checks = [any(detector.accepts(m) for m in detector.match(read_audio(path))) for path in paths]
        if not all(checks):
            raise RuntimeError("Bundled sound reference check failed")
        with AudioBackend() as backend:
            devices = list(backend.p.get_loopback_device_info_generator())
        report = {"reference_checks": checks, "loopback_devices": len(devices),
                  "game_windows": len(list_windows()), "keyboard_available": "k" in pyautogui.KEYBOARD_KEYS}
        args.self_check.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")
    App(args.settings).mainloop()


if __name__ == "__main__":
    main()
