"""Windows Tk lifecycle checks with fake devices and no real keyboard input."""
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch, Mock

from app_settings import load
import gui
from windows_control import GameWindow


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "settings.yaml"
        self.window = GameWindow(123, 44, "World of Warcraft")
        backend = Mock()
        backend.__enter__ = Mock(return_value=backend)
        backend.__exit__ = Mock(return_value=False)
        backend.p.get_loopback_device_info_generator.return_value = iter([])
        self.patches = [patch("gui.list_windows", return_value=[self.window]),
                        patch("gui.AudioBackend", return_value=backend)]
        for p in self.patches:
            p.start()
        gui.ctk.set_appearance_mode("dark")
        self.app = gui.App(self.path)
        self.app.withdraw()
        self.pump(.3)

    def pump(self, duration):
        end = time.monotonic() + duration
        while time.monotonic() < end:
            self.app.update()
            time.sleep(.01)

    def tearDown(self):
        try:
            if self.app.winfo_exists():
                if self.app.session:
                    self.app.session.stop()
                    self.app.worker.join(2)
                # CTk schedules global DPI callbacks; cancel them before creating
                # the next test's independent Tcl interpreter.
                for callback in self.app.tk.call("after", "info"):
                    self.app.tk.call("after", "cancel", callback)
                self.app.destroy()
        finally:
            for p in reversed(self.patches):
                p.stop()
            self.directory.cleanup()

    def test_settings_validation_and_persistence(self):
        self.app.open_settings()
        dialog = self.app.dialog
        self.pump(.15)
        entry = dialog.entries["ACTION_KEY"][0]
        entry.delete(0, "end")
        entry.insert(0, "not a key")
        dialog.commit()
        self.assertIn("ACTION_KEY", dialog.error.cget("text"))
        entry.delete(0, "end")
        entry.insert(0, "f2")
        dialog.commit()
        self.assertEqual(load(self.path)["ACTION_KEY"], "f2")
        self.assertEqual(self.app.settings["ACTION_KEY"], "f2")

    def test_stop_button_waits_for_worker_then_can_restart(self):
        sessions = []

        class Session:
            def __init__(self, cfg, window, emit):
                from threading import Event
                self.stop_event = Event()
                self.emit = emit
                sessions.append(self)

            def run(self):
                self.emit("state", "Listening")
                self.stop_event.wait(2)
                self.emit("done", None)

            def stop(self):
                self.stop_event.set()

        with patch("gui.BotSession", Session):
            for _ in range(2):
                self.app.toggle()
                self.assertIsNotNone(self.app.worker)
                self.assertEqual(self.app.settings_button.cget("state"), "disabled")
                self.app.toggle()
                self.pump(.2)
                self.assertIsNone(self.app.worker)
                self.assertEqual(self.app.start_button.cget("state"), "normal")
        self.assertEqual(len(sessions), 2)

    def test_missing_saved_device_needs_explicit_selection(self):
        self.app.settings["OUTPUT_DEVICE_NAME"] = "Disconnected output"
        self.app.settings["OUTPUT_DEVICE_INDEX"] = 99
        self.app.discovered(([self.window], [], []))
        self.assertNotIn(self.app.audio_combo.get(), self.app.devices)
        with patch("gui.messagebox.showerror") as error:
            self.app.toggle()
        error.assert_called_once()
        self.assertIsNone(self.app.worker)


if __name__ == "__main__":
    unittest.main()
